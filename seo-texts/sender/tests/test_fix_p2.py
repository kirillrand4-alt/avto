"""FIX П2 (доставляемость/целостность) — тесты дефектов из REVIEW-FINDINGS.

Каждый тест писался ПАДАЮЩИМ до фикса и зелёным после:
  П2.1 — STARTTLS на 587 до login (пароль не ходит открытым текстом);
  П2.2 — CRLF в значениях заголовков санируется (инъекция/ядовитое письмо);
  П2.3 — fail-safe: сбой чтения паузы ящика исключает ящик из отправки;
  П2.4 — fail-safe: сбой оценки гейтов останавливает волну тика;
  П2.5 — bounce-гейт каденции считается ПО ПОЛУЧАТЕЛЮ, а не по всему домену;
  П2.6 — next_step_for продвигается по отправленным шагам (не вечный шаг 0);
  П2.7 — day_key счётчиков ящика = дата в зоне конфига (не UTC).
"""

import os
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import pytest

sys.path.insert(
    0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
)

from sender.cadence import Cadence  # noqa: E402
from sender.config import Config  # noqa: E402
from sender.dtos import (  # noqa: E402
    CampaignIn, EventIn, MailboxState, MessageIn, RecipientIn, RenderedMessage,
    SequenceStepIn,
)
from sender.errors import SendError  # noqa: E402
from sender.orchestrator import Orchestrator  # noqa: E402
from sender.sender import Sender  # noqa: E402
from sender.store import Store  # noqa: E402
from sender.suppression import Suppression  # noqa: E402
from sender.tests.test_config import BASE_YAML  # noqa: E402

UTC = timezone.utc
IN_WINDOW = datetime(2026, 7, 21, 8, 0, tzinfo=UTC)  # вторник 11:00 МСК


# --------------------------------------------------------------------------- #
# Фикстуры (реальный Store + Config из BASE_YAML)
# --------------------------------------------------------------------------- #
@pytest.fixture
def config(tmp_path):
    for i in range(1, 6):
        os.environ.setdefault(f"BOX{i}_PASSWORD", "x")
    os.environ["UNSUB_SIGNING_SECRET"] = "test_secret_key_min_32_chars_long"
    path = tmp_path / "config.yaml"
    path.write_text(BASE_YAML.replace("db.db", str(tmp_path / "t.db")),
                    encoding="utf-8")
    return Config.load(str(path))


@pytest.fixture
def config587(tmp_path):
    """Как config, но box1 на 587 (submission) — для STARTTLS-теста."""
    for i in range(1, 6):
        os.environ.setdefault(f"BOX{i}_PASSWORD", "x")
    os.environ["UNSUB_SIGNING_SECRET"] = "test_secret_key_min_32_chars_long"
    yaml = BASE_YAML.replace("db.db", str(tmp_path / "t.db"))
    yaml = yaml.replace("smtp_port: 465", "smtp_port: 587", 1)  # только box1
    path = tmp_path / "config587.yaml"
    path.write_text(yaml, encoding="utf-8")
    return Config.load(str(path))


@pytest.fixture
def store(tmp_path):
    s = Store(str(tmp_path / "t.db"))
    s.init_schema()
    yield s
    s.close()


@pytest.fixture
def suppression(store):
    return Suppression(store)


@dataclass(frozen=True)
class _Decision:
    tripped: bool = False


class _Gates:
    def check_global(self):
        return _Decision()

    def check_domain(self, domain, campaign_id=None):
        return _Decision()

    def check_mailbox(self, mailbox_id):
        return _Decision()


class _RecordingClient:
    """SMTP-клиент, пишущий последовательность вызовов."""

    def __init__(self, calls, *, starttls_exc=None):
        self._calls = calls
        self._starttls_exc = starttls_exc

    def starttls(self):
        if self._starttls_exc is not None:
            raise self._starttls_exc
        self._calls.append("starttls")

    def ehlo(self):
        self._calls.append("ehlo")

    def login(self, *a):
        self._calls.append("login")

    def sendmail(self, frm, to, data):
        self._calls.append("sendmail")
        self.last_mime = data

    def quit(self):
        pass


def _seed_mailbox(store, mailbox_id="box1@rusprom.ru", day=IN_WINDOW):
    store.upsert_mailbox_state(MailboxState(
        mailbox_id=mailbox_id, provider="yandex",
        day_key=day.strftime("%Y-%m-%d"), sent_today=0, sent_total=0,
        ramp_day=30, daily_limit=30, last_sent_at=None,
        paused=False, pause_reason=None))


def _seed_message(store, email="p2@x.ru", key="p2k"):
    cid = store.create_campaign(CampaignIn(
        name="П2", legal_entity="ООО «Руспром»", legal_inn="2221239841"))
    sid = store.add_step(SequenceStepIn(
        campaign_id=cid, step_index=0, delay_hours=0,
        subject_tmpl="Т", body_tmpl="Б"))
    rid = store.upsert_recipient(RecipientIn(email=email, domain="x.ru"))
    mid, _ = store.enqueue_message(MessageIn(
        idempotency_key=key, campaign_id=cid, recipient_id=rid,
        sequence_step_id=sid, scheduled_at=IN_WINDOW - timedelta(hours=1)))
    return cid, sid, rid, mid


# --------------------------------------------------------------------------- #
# П2.1 — STARTTLS на 587
# --------------------------------------------------------------------------- #
def test_p21_starttls_called_before_login_on_587(config587, store, suppression):
    calls = []
    sndr = Sender(config587, store, suppression, _Gates(), dry_run=False)
    sndr._smtp_opener = lambda host, port, use_ssl: _RecordingClient(calls)
    os.environ["BOX1_PASSWORD"] = "secret"
    _seed_mailbox(store)
    _cid, _sid, _rid, mid = _seed_message(store)
    claimed = store.claim_due_messages(
        now=IN_WINDOW, mailbox_ids=["box1@rusprom.ru"], limit=1)

    result = sndr.send(claimed[0], RenderedMessage(subject="Т", body="Б"),
                       "box1@rusprom.ru", now=IN_WINDOW)
    assert result.ok
    assert "starttls" in calls, f"STARTTLS не вызван: {calls}"
    assert calls.index("starttls") < calls.index("login")


def test_p21_starttls_refusal_blocks_password(config587, store, suppression):
    """Сервер не поддерживает STARTTLS → пароль НЕ отправляется, SendError."""
    import smtplib
    calls = []
    sndr = Sender(config587, store, suppression, _Gates(), dry_run=False)
    sndr._smtp_opener = lambda host, port, use_ssl: _RecordingClient(
        calls, starttls_exc=smtplib.SMTPException("no STARTTLS"))
    os.environ["BOX1_PASSWORD"] = "secret"
    _seed_mailbox(store)
    _cid, _sid, _rid, mid = _seed_message(store)
    claimed = store.claim_due_messages(
        now=IN_WINDOW, mailbox_ids=["box1@rusprom.ru"], limit=1)

    with pytest.raises(SendError):
        sndr.send(claimed[0], RenderedMessage(subject="Т", body="Б"),
                  "box1@rusprom.ru", now=IN_WINDOW)
    assert "login" not in calls  # пароль в открытую не ушёл


def test_p21_no_starttls_on_465_ssl(config, store, suppression):
    """На 465 (implicit SSL) starttls НЕ дёргаем."""
    calls = []
    sndr = Sender(config, store, suppression, _Gates(), dry_run=False)
    sndr._smtp_opener = lambda host, port, use_ssl: _RecordingClient(calls)
    os.environ["BOX1_PASSWORD"] = "secret"
    _seed_mailbox(store)
    _cid, _sid, _rid, mid = _seed_message(store)
    claimed = store.claim_due_messages(
        now=IN_WINDOW, mailbox_ids=["box1@rusprom.ru"], limit=1)
    result = sndr.send(claimed[0], RenderedMessage(subject="Т", body="Б"),
                       "box1@rusprom.ru", now=IN_WINDOW)
    assert result.ok
    assert "starttls" not in calls


# --------------------------------------------------------------------------- #
# П2.2 — CRLF-санация заголовков
# --------------------------------------------------------------------------- #
def test_p22_crlf_in_subject_sanitized_not_poison(config, store, suppression):
    """Тема с \\r\\n (инъекция из merge-полей CSV) не роняет отправку и не
    попадает в MIME отдельными заголовками. Раньше EmailMessage бросал
    ValueError → письмо зависало в 'sending' и травило каждый тик."""
    calls = []
    sndr = Sender(config, store, suppression, _Gates(), dry_run=False)
    client_box = {}

    def opener(host, port, use_ssl):
        c = _RecordingClient(calls)
        client_box["c"] = c
        return c

    sndr._smtp_opener = opener
    os.environ["BOX1_PASSWORD"] = "secret"
    _seed_mailbox(store)
    _cid, _sid, _rid, mid = _seed_message(store)
    claimed = store.claim_due_messages(
        now=IN_WINDOW, mailbox_ids=["box1@rusprom.ru"], limit=1)

    evil = "Прайс\r\nBcc: attacker@evil.com\r\nX-Inject: 1"
    result = sndr.send(claimed[0], RenderedMessage(subject=evil, body="Б"),
                       "box1@rusprom.ru", now=IN_WINDOW)
    assert result.ok
    mime = client_box["c"].last_mime
    if isinstance(mime, str):
        mime = mime.encode("utf-8")
    from email import message_from_bytes
    parsed = message_from_bytes(mime)
    # Инъекция не породила НАСТОЯЩИХ заголовков…
    assert parsed["Bcc"] is None
    assert parsed["X-Inject"] is None
    # …а тема стала одной логической строкой с текстом внутри значения.
    from email.header import decode_header, make_header
    subject = str(make_header(decode_header(parsed["Subject"])))
    assert "\n" not in subject and "\r" not in subject
    assert "attacker@evil.com" in subject  # остался ТЕКСТОМ, не заголовком


def test_p22_strip_crlf_helper():
    from sender.sender import _strip_crlf
    assert _strip_crlf("a\r\nb\nc") == "a b c"
    assert _strip_crlf(None) == ""
    assert _strip_crlf(" ok ") == " ok "


# --------------------------------------------------------------------------- #
# П2.3 — fail-safe при сбое чтения паузы ящика
# --------------------------------------------------------------------------- #
class _BrokenStateStore:
    """Обёртка стора: get_mailbox_state падает для выбранного ящика."""

    def __init__(self, inner, broken_id):
        self._inner = inner
        self._broken = broken_id

    def get_mailbox_state(self, mailbox_id):
        if mailbox_id == self._broken:
            raise RuntimeError("db glitch")
        return self._inner.get_mailbox_state(mailbox_id)

    def __getattr__(self, name):
        return getattr(self._inner, name)


def _make_orch(config, base_store, suppression, **overrides):
    store = overrides.get("store", base_store)
    class _Imap:
        def poll_once(self, mid):
            return []

    class _GatesAll:
        def evaluate_all(self):
            return []

        def check_global(self):
            return _Decision()

        def check_mailbox(self, mid):
            return _Decision()

        def check_domain(self, d, c=None):
            return _Decision()

    class _Warmup:
        def run_cycle(self, mid, *, now):
            from sender.dtos import WarmupCycleResult
            return WarmupCycleResult(mid, 0, 0, None)

    class _Analytics:
        pass

    sndr = overrides.get("sender") or Sender(
        config, store, suppression, _GatesAll(), dry_run=True)
    cadence = Cadence(config, store, suppression)
    return Orchestrator(
        config, store, sndr, cadence,
        overrides.get("gates", _GatesAll()), _Imap(), _Warmup(), _Analytics(),
        personalizer=overrides.get("personalizer"),
    )


def test_p23_broken_pause_read_excludes_mailbox(config, store, suppression):
    """Сбой чтения mailbox_state → ящик НЕ считается активным (раньше ящик
    попадал в отправку, даже будучи на паузе)."""
    _seed_mailbox(store)
    broken = _BrokenStateStore(store, "box1@rusprom.ru")
    orch = _make_orch(config, store, suppression, store=broken)
    active = orch._active_mailbox_ids()
    assert "box1@rusprom.ru" not in active
    assert len(active) > 0  # остальные ящики живы


def test_p23_failed_pause_write_holds_mailbox_in_memory(
        config, store, suppression):
    """Гейт велел паузить, а set_mailbox_paused упал → ящик держится вне
    отправки in-memory (раньше следующий тик слал с трипнутого ящика)."""
    _seed_mailbox(store)

    class _NoPauseWriteStore:
        def __init__(self, inner):
            self._inner = inner

        def set_mailbox_paused(self, *a, **k):
            raise RuntimeError("db locked")

        def __getattr__(self, name):
            return getattr(self._inner, name)

    orch = _make_orch(config, store, suppression,
                      store=_NoPauseWriteStore(store))
    orch._safe_pause("box1@rusprom.ru", "gate_trip:test", paused=True)
    assert "box1@rusprom.ru" not in orch._active_mailbox_ids()

    # Успешная запись (стор ожил) снимает in-memory метку.
    orch.store = store
    orch._safe_pause("box1@rusprom.ru", None, paused=False)
    assert "box1@rusprom.ru" in orch._active_mailbox_ids()


# --------------------------------------------------------------------------- #
# П2.4 — fail-safe при сбое оценки гейтов
# --------------------------------------------------------------------------- #
def test_p24_gates_failure_stops_tick_wave(config, store, suppression):
    """gates.evaluate_all упал → тик НЕ шлёт (раньше волна летела без защиты)."""
    _seed_mailbox(store)
    _cid, _sid, _rid, mid = _seed_message(store)

    class _FailingGates:
        def evaluate_all(self):
            raise RuntimeError("gates db down")

        def check_global(self):
            return _Decision()

        def check_mailbox(self, mid):
            return _Decision()

        def check_domain(self, d, c=None):
            return _Decision()

    orch = _make_orch(config, store, suppression, gates=_FailingGates())
    calls = []
    orch.sender.send = lambda *a, **k: calls.append(a)  # шпион вместо отправки
    result = orch.tick(now=IN_WINDOW)
    assert result.sent == 0
    assert calls == []  # send не вызывался вовсе — волна остановлена
    # письмо не тронуто (осталось scheduled, не sending/failed)
    assert store.get_message(mid).status == "scheduled"


# --------------------------------------------------------------------------- #
# П2.5 — bounce-гейт по получателю, не по домену
# --------------------------------------------------------------------------- #
def test_p25_not_bounced_gate_is_per_recipient(config, store, suppression):
    """Bounce соседа по домену (mail.ru — общий хостинг!) не должен резать
    остальных получателей домена."""
    cadence = Cadence(config, store, suppression)
    cid = store.create_campaign(CampaignIn(
        name="c", legal_entity="ООО «Руспром»", legal_inn="2221239841"))
    sid = store.add_step(SequenceStepIn(
        campaign_id=cid, step_index=1, delay_hours=24,
        subject_tmpl="s", body_tmpl="b", engagement_gate="not_bounced"))
    step = store.get_steps(cid)[0]
    rid_a = store.upsert_recipient(RecipientIn(email="a@mail.ru", domain="mail.ru"))
    rid_b = store.upsert_recipient(RecipientIn(email="b@mail.ru", domain="mail.ru"))
    store.append_event(EventIn(
        dedup_key="bounce:a", event_type="bounce", event_ts=IN_WINDOW,
        recipient_id=rid_a, campaign_id=cid))

    dec_a = cadence.evaluate_gate(step, store.get_recipient(rid_a), cid)
    dec_b = cadence.evaluate_gate(step, store.get_recipient(rid_b), cid)
    assert dec_a.action == "skip"   # свой bounce — скип
    assert dec_b.action == "send"   # чужой bounce не заражает домен


# --------------------------------------------------------------------------- #
# П2.6 — next_step_for продвигается, а не вечный шаг 0
# --------------------------------------------------------------------------- #
def test_p26_next_step_advances_past_sent_steps(config, store, suppression):
    cadence = Cadence(config, store, suppression)
    cid = store.create_campaign(CampaignIn(
        name="c", legal_entity="ООО «Руспром»", legal_inn="2221239841"))
    store.add_step(SequenceStepIn(
        campaign_id=cid, step_index=0, delay_hours=0,
        subject_tmpl="s0", body_tmpl="b0"))
    store.add_step(SequenceStepIn(
        campaign_id=cid, step_index=1, delay_hours=48,
        subject_tmpl="s1", body_tmpl="b1"))
    steps = sorted(store.get_steps(cid), key=lambda s: s.step_index)
    rid = store.upsert_recipient(RecipientIn(email="n@x.ru", domain="x.ru"))

    assert cadence.next_step_for(rid, cid).step_index == 0

    mid, _ = store.enqueue_message(MessageIn(
        idempotency_key="ns0", campaign_id=cid, recipient_id=rid,
        sequence_step_id=steps[0].id, scheduled_at=IN_WINDOW))
    store.append_event(EventIn(
        dedup_key=f"send:{mid}", event_type="sent", event_ts=IN_WINDOW,
        message_id=mid, recipient_id=rid, campaign_id=cid))

    nxt = cadence.next_step_for(rid, cid)
    assert nxt is not None and nxt.step_index == 1  # раньше — вечный шаг 0

    mid2, _ = store.enqueue_message(MessageIn(
        idempotency_key="ns1", campaign_id=cid, recipient_id=rid,
        sequence_step_id=steps[1].id, scheduled_at=IN_WINDOW))
    store.append_event(EventIn(
        dedup_key=f"send:{mid2}", event_type="sent", event_ts=IN_WINDOW,
        message_id=mid2, recipient_id=rid, campaign_id=cid))
    assert cadence.next_step_for(rid, cid) is None  # цепочка пройдена


def test_p26_next_step_stops_on_reply(config, store, suppression):
    cadence = Cadence(config, store, suppression)
    cid = store.create_campaign(CampaignIn(
        name="c", legal_entity="ООО «Руспром»", legal_inn="2221239841"))
    store.add_step(SequenceStepIn(
        campaign_id=cid, step_index=0, delay_hours=0,
        subject_tmpl="s0", body_tmpl="b0"))
    rid = store.upsert_recipient(RecipientIn(email="r2@x.ru", domain="x.ru"))
    store.append_event(EventIn(
        dedup_key="rr", event_type="reply", event_ts=IN_WINDOW,
        recipient_id=rid, campaign_id=cid))
    assert cadence.next_step_for(rid, cid) is None


# --------------------------------------------------------------------------- #
# П2.7 — day_key в зоне конфига
# --------------------------------------------------------------------------- #
def test_p27_increment_sent_honors_passed_day_key(store):
    _seed_mailbox(store)
    # 21:30 UTC вторника = 00:30 МСК среды — по конфигу это уже «завтра».
    late = datetime(2026, 7, 21, 21, 30, tzinfo=UTC)
    st = store.increment_sent("box1@rusprom.ru", now=late, day_key="2026-07-22")
    assert st.day_key == "2026-07-22"
    assert st.sent_today == 1          # новый день → счётчик с единицы
    assert st.ramp_day == 31           # рамп-день продвинулся


def test_p27_increment_sent_default_stays_utc(store):
    """Без day_key поведение прежнее (обратная совместимость юнитов)."""
    _seed_mailbox(store)
    st = store.increment_sent("box1@rusprom.ru", now=IN_WINDOW)
    assert st.day_key == IN_WINDOW.strftime("%Y-%m-%d")
    assert st.sent_today == 1


def test_p27_sender_passes_config_tz_day_key(config, store, suppression, monkeypatch):
    """send() передаёт в increment_sent день по зоне конфига (МСК)."""
    sndr = Sender(config, store, suppression, _Gates(), dry_run=True)
    sndr._smtp_opener = lambda h, p, s: _RecordingClient([])
    _seed_mailbox(store)
    _cid, _sid, _rid, mid = _seed_message(store)
    claimed = store.claim_due_messages(
        now=IN_WINDOW, mailbox_ids=["box1@rusprom.ru"], limit=1)

    seen = {}
    orig = store.increment_sent

    def spy(mailbox_id, *, now, day_key=None):
        seen["day_key"] = day_key
        return orig(mailbox_id, now=now, day_key=day_key)

    monkeypatch.setattr(store, "increment_sent", spy)
    sndr.send(claimed[0], RenderedMessage(subject="Т", body="Б"),
              "box1@rusprom.ru", now=IN_WINDOW)
    assert seen["day_key"] == sndr._day_key(IN_WINDOW)
