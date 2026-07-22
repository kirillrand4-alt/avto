"""Задача 5: фиксы подтверждённых ревью-хвостов — тесты.

Покрывают: TOCTOU-перепроверку suppression перед _deliver; word-boundary
атрибуции; окно метрик гейтов (window_days) + агрегатный путь; сдвиг
base_time при skip в каденции; auth (лок перебора, атомарная смена пароля,
disable_2fa разлогинивает); ramp-устойчивость; probe_from-валидацию.
"""

import os
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import pytest

sys.path.insert(
    0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
)

from sender.auth import Auth, AuthError  # noqa: E402
from sender.config import Config  # noqa: E402
from sender.dtos import (  # noqa: E402
    CampaignIn, EventIn, MailboxState, MessageIn, RecipientIn, RenderedMessage,
    SequenceStepIn,
)
from sender.errors import SuppressedError, ValidationError  # noqa: E402
from sender.gates import Gates  # noqa: E402
from sender.personalize import Personalizer  # noqa: E402
from sender.sender import Sender  # noqa: E402
from sender.store import Store  # noqa: E402
from sender.suppression import Suppression  # noqa: E402
from sender.tests.test_config import BASE_YAML  # noqa: E402

UTC = timezone.utc
IN_WINDOW = datetime(2026, 7, 21, 8, 0, tzinfo=UTC)


@pytest.fixture
def config(tmp_path):
    for i in range(1, 6):
        os.environ.setdefault(f"BOX{i}_PASSWORD", "x")
    os.environ["UNSUB_SIGNING_SECRET"] = "test_secret_key_min_32_chars_long"
    path = tmp_path / "c.yaml"
    path.write_text(BASE_YAML.replace("/tmp/sender.db", str(tmp_path / "t.db")),
                    encoding="utf-8")
    return Config.load(str(path))


@pytest.fixture
def store(tmp_path):
    s = Store(str(tmp_path / "t.db"))
    s.init_schema()
    yield s
    s.close()


@dataclass(frozen=True)
class _D:
    tripped: bool = False


class _Gates:
    def check_global(self):
        return _D()

    def check_domain(self, d, c=None):
        return _D()

    def check_mailbox(self, m):
        return _D()


# -- TOCTOU: suppression между claim-проверкой и SMTP -------------------------- #
def test_toctou_suppression_added_midway_blocks_delivery(config, store):
    """Suppress появляется ПОСЛЕ шага (3), но ДО _deliver → письмо не уходит."""
    supp = Suppression(store)
    sndr = Sender(config, store, supp, _Gates(), dry_run=True)
    sent = []

    class _Client:
        def login(self, *a): ...

        def sendmail(self, f, t, d):
            sent.append(t)

        def quit(self): ...

    sndr._smtp_opener = lambda h, p, s: _Client()
    cid = store.create_campaign(CampaignIn(
        name="c", legal_entity="ООО «Руспром»", legal_inn="2221239841"))
    sid = store.add_step(SequenceStepIn(
        campaign_id=cid, step_index=0, delay_hours=0,
        subject_tmpl="s", body_tmpl="b"))
    rid = store.upsert_recipient(RecipientIn(email="t@x.ru", domain="x.ru"))
    store.upsert_mailbox_state(MailboxState(
        mailbox_id="box1@rusprom.ru", provider="yandex",
        day_key=IN_WINDOW.strftime("%Y-%m-%d"), sent_today=0, sent_total=0,
        ramp_day=30, daily_limit=30, last_sent_at=None, paused=False,
        pause_reason=None))
    mid, _ = store.enqueue_message(MessageIn(
        idempotency_key="k", campaign_id=cid, recipient_id=rid,
        sequence_step_id=sid, scheduled_at=IN_WINDOW))
    msg = store.get_message(mid)

    # Эмуляция IMAP-ридера: suppress добавляется при построении заголовков —
    # т.е. ПОСЛЕ первичной проверки шага (3), до доставки.
    orig = sndr.build_headers

    def hooked(*a, **k):
        supp.add_email("t@x.ru", "bounce_hard")
        return orig(*a, **k)

    sndr.build_headers = hooked
    with pytest.raises(SuppressedError):
        sndr.send(msg, RenderedMessage(subject="s", body="b"),
                  "box1@rusprom.ru", now=IN_WINDOW)
    assert sent == []  # SMTP не тронут
    assert store.get_message(mid).status == "skipped"


# -- Атрибуция: границы слова -------------------------------------------------- #
def test_attribution_substring_entity_not_enough():
    fields = {"legal_entity": "Русь", "legal_inn": "7700000000"}
    body = "Компания Русьхолдинг работает с ИНН 7700000000."
    out = Personalizer._ensure_attribution(body, fields)
    assert "\n--\n" in out  # футер добавлен: «Русь» внутри слова не считается


def test_attribution_exact_word_ok():
    fields = {"legal_entity": "Русь", "legal_inn": "7700000000"}
    body = "Оферта. Русь, ИНН 7700000000."
    assert Personalizer._ensure_attribution(body, fields) == body


# -- Гейты: окно метрик + агрегат ---------------------------------------------- #
def test_gates_window_excludes_history(config, store):
    """Старый «чистый» объём вне окна больше не разбавляет свежий всплеск."""
    gates = Gates(config, store)
    assert gates._cfg.window_days == 14
    rid = store.upsert_recipient(RecipientIn(email="w@dom.ru", domain="dom.ru"))
    old = datetime.now(UTC) - timedelta(days=60)
    now = datetime.now(UTC) - timedelta(hours=1)
    # история: 200 чистых отправок 60 дней назад
    for i in range(200):
        store.append_event(EventIn(
            dedup_key=f"old:{i}", event_type="sent", event_ts=old,
            recipient_id=rid, mailbox_id="box1@rusprom.ru"))
    # свежий всплеск: 20 отправок, 5 баунсов (25% >> порога)
    for i in range(20):
        store.append_event(EventIn(
            dedup_key=f"new:{i}", event_type="sent", event_ts=now,
            recipient_id=rid, mailbox_id="box1@rusprom.ru"))
    for i in range(5):
        store.append_event(EventIn(
            dedup_key=f"b:{i}", event_type="bounce", event_ts=now,
            recipient_id=rid, mailbox_id="box1@rusprom.ru"))
    d = gates.check_mailbox("box1@rusprom.ru")
    # min_volume в BASE_YAML <= 20? если нет — гейт не значим; проверяем rate
    assert d.value >= 20.0  # 5/20=25%, а не 5/220=2.3%


def test_gates_grouped_matches_pointwise(config, store):
    """Агрегатный путь evaluate_all даёт те же домен-вердикты, что поштучный."""
    gates = Gates(config, store)
    rid = store.upsert_recipient(RecipientIn(email="a@agg.ru", domain="agg.ru"))
    now = datetime.now(UTC) - timedelta(hours=2)
    for i in range(30):
        store.append_event(EventIn(
            dedup_key=f"s:{i}", event_type="sent", event_ts=now,
            recipient_id=rid))
    for i in range(4):
        store.append_event(EventIn(
            dedup_key=f"bb:{i}", event_type="bounce", event_ts=now,
            recipient_id=rid))
    decisions = gates.evaluate_all()
    dom = [d for d in decisions
           if d.scope == "domain" and d.target == "agg.ru"
           and d.metric == "bounce_rate"]
    assert dom, "домен agg.ru не оценён"
    point_b, _point_c = gates._domain_metrics("agg.ru")
    assert dom[0].value == point_b.value
    assert dom[0].tripped == point_b.tripped


# -- Каденция: skip двигает base_time ------------------------------------------- #
def test_cadence_skip_advances_base_time(config, store):
    from sender.cadence import Cadence
    supp = Suppression(store)
    cadence = Cadence(config, store, supp)
    cid = store.create_campaign(CampaignIn(
        name="c", legal_entity="ООО «Руспром»", legal_inn="2221239841"))
    store.add_step(SequenceStepIn(campaign_id=cid, step_index=0, delay_hours=0,
                                  subject_tmpl="s0", body_tmpl="b0"))
    store.add_step(SequenceStepIn(campaign_id=cid, step_index=1, delay_hours=96,
                                  subject_tmpl="s1", body_tmpl="b1",
                                  engagement_gate="not_bounced"))
    store.add_step(SequenceStepIn(campaign_id=cid, step_index=2, delay_hours=96,
                                  subject_tmpl="s2", body_tmpl="b2"))
    rid = store.upsert_recipient(RecipientIn(email="sk@x.ru", domain="x.ru"))
    # bounce у получателя → шаг 1 скипается
    store.append_event(EventIn(dedup_key="b1", event_type="bounce",
                               event_ts=IN_WINDOW, recipient_id=rid,
                               campaign_id=cid))
    msgs = cadence.plan_for_recipient(store.get_recipient(rid), cid,
                                      now=IN_WINDOW)
    steps = {m.sequence_step_id for m in msgs}
    assert len(msgs) == 2  # шаги 0 и 2 (1 скипнут)
    # шаг 2 обязан лечь ПОЗЖЕ, чем «база + его delay» — т.е. delay скипнутого
    # шага 1 не схлопнулся (раньше шаг 2 планировался на ~4 суток раньше).
    last = max(m.scheduled_at for m in msgs)
    assert last >= IN_WINDOW + timedelta(hours=96 + 96 - 24)  # с запасом джиттера


# -- Auth: лок перебора, атомарная смена, disable_2fa --------------------------- #
def test_auth_bruteforce_lockout(store):
    auth = Auth(store)
    auth.create_user(username="op", password="password123", role="owner")
    for _ in range(5):
        with pytest.raises(AuthError):
            auth.login(username="op", password="wrong")
    # после 5 неудач — лок: даже ВЕРНЫЙ пароль отклоняется
    with pytest.raises(AuthError):
        auth.login(username="op", password="password123")
    st = store.auth_throttle_state("op")
    assert st["failed"] >= 5 and st["locked_until"] is not None


def test_auth_lockout_resets_on_success(store):
    auth = Auth(store)
    auth.create_user(username="ok", password="password123", role="owner")
    for _ in range(3):
        with pytest.raises(AuthError):
            auth.login(username="ok", password="wrong")
    token = auth.login(username="ok", password="password123")  # ещё не лок
    assert token
    assert store.auth_throttle_state("ok")["failed"] == 0


def test_auth_password_change_atomic_and_revokes(store):
    auth = Auth(store)
    uid = auth.create_user(username="pw", password="password123", role="owner")["user_id"]
    token = auth.login(username="pw", password="password123")
    assert auth.resolve(token) is not None
    auth.set_password(uid, "newpassword456")
    assert auth.resolve(token) is None  # старая сессия отозвана атомарно


def test_auth_disable_2fa_revokes_sessions(store):
    auth = Auth(store)
    uid = auth.create_user(username="tf", password="password123", role="owner")["user_id"]
    token = auth.login(username="tf", password="password123")
    auth.disable_2fa(uid)
    assert auth.resolve(token) is None


# -- ramp: мусор в конфиге ------------------------------------------------------- #
def test_ramp_garbage_tolerant():
    from sender.ramp import curve_value
    assert curve_value([5, 10], None) == 0
    assert curve_value([5, 10], "abc") == 0
    assert curve_value([5, "x"], 1) == 0
    assert curve_value([5, 10], 1) == 10


# -- validation: probe_from при включённой пробе --------------------------------- #
def test_validation_probe_from_guard():
    from sender.validation import Validation

    class _Cfg:
        def __init__(self, probe, frm):
            self._d = {"validation.smtp_probe": probe,
                       "validation.probe_from": frm}

        def get(self, k, default=None):
            return self._d.get(k, default)

    with pytest.raises(ValidationError):
        Validation(_Cfg(True, "probe@localhost"))
    Validation(_Cfg(False, "probe@localhost"))  # выключено — дефолт ок
    Validation(_Cfg(True, "probe@rusprom.ru"))  # валидный адрес ок
