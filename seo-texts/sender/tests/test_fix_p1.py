"""FIX П1 (юридика ФЗ-38) — тесты дефектов из REVIEW-FINDINGS.

Каждый тест писался ПАДАЮЩИМ до фикса и зелёным после:
  П1.1 — нормализация email/домена/ИНН: upsert + SQL-сравнения suppression;
  П1.2 — вечная отписка: апгрейд поверх TTL-записи, неистекаемость, запрет снятия;
  П1.4 — one-click отвечает честным кодом (не 200 при провале);
  П1.5 — has_reply перепроверяется непосредственно перед SMTP;
  П1.6 — атрибуция: частичное совпадение (только ИНН в теле) не отменяет футер;
  БОНУС — токен/URL отписки sender.py совместимы с unsub_server (сверх списка:
          боевое письмо строило `?token=` + свой формат, сервер ждал `?t=` +
          формат sender.tokens — ссылка отписки не работала вообще).
"""

import os
import sqlite3
import sys
import threading
import time as _time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlparse
from urllib.request import Request, urlopen

import pytest

sys.path.insert(
    0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
)

from sender.config import Config  # noqa: E402
from sender.dtos import (  # noqa: E402
    CampaignIn, EventIn, MailboxState, MessageIn, RecipientIn, RenderedMessage,
    SequenceStepIn, SuppressionIn,
)
from sender.errors import SuppressedError, ValidationError  # noqa: E402
from sender.personalize import Personalizer  # noqa: E402
from sender.sender import Sender  # noqa: E402
from sender.store import Store, _now_iso, _to_iso  # noqa: E402
from sender.suppression import Suppression  # noqa: E402
from sender.tests.test_config import BASE_YAML  # noqa: E402
from sender.unsub import Unsub  # noqa: E402
from sender.unsub_server import make_server  # noqa: E402

UTC = timezone.utc
# Вторник 11:00 МСК — внутри окна отправки BASE_YAML (09:30-17:30 Пн-Пт МСК).
IN_WINDOW = datetime(2026, 7, 21, 8, 0, tzinfo=UTC)


# --------------------------------------------------------------------------- #
# Фикстуры: реальные Store/Config/Suppression (SQLite в tmp_path).
# --------------------------------------------------------------------------- #
@pytest.fixture
def config(tmp_path):
    os.environ.setdefault("BOX1_PASSWORD", "x")
    os.environ.setdefault("BOX2_PASSWORD", "x")
    os.environ.setdefault("BOX3_PASSWORD", "x")
    os.environ.setdefault("BOX4_PASSWORD", "x")
    os.environ.setdefault("BOX5_PASSWORD", "x")
    os.environ["UNSUB_SIGNING_SECRET"] = "test_secret_key_min_32_chars_long"
    path = tmp_path / "config.yaml"
    path.write_text(BASE_YAML.replace("db.db", str(tmp_path / "t.db")),
                    encoding="utf-8")
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
    """Гейты-пустышки: ничего не срабатывает."""

    def check_global(self):
        return _Decision()

    def check_domain(self, domain, campaign_id=None):
        return _Decision()

    def check_mailbox(self, mailbox_id):
        return _Decision()


class _CountingOpener:
    """Стаб SMTP-клиента: считает sendmail, наружу не ходит."""

    def __init__(self):
        self.sent = []

    def __call__(self, host, port, use_ssl):
        opener = self

        class _Client:
            def login(self, *a, **k):
                pass

            def sendmail(self, frm, to, data):
                opener.sent.append((frm, to, data))

            def quit(self):
                pass

        return _Client()


@pytest.fixture
def sender_env(config, store, suppression):
    """Sender с реальным Store и стабом SMTP + посеянная кампания/шаг/ящик."""
    sndr = Sender(config, store, suppression, _Gates(), dry_run=True)
    opener = _CountingOpener()
    sndr._smtp_opener = opener

    cid = store.create_campaign(CampaignIn(
        name="П1", legal_entity="ООО «Руспром»", legal_inn="2221239841"))
    sid = store.add_step(SequenceStepIn(
        campaign_id=cid, step_index=0, delay_hours=0,
        subject_tmpl="Тема", body_tmpl="Тело"))
    store.upsert_mailbox_state(MailboxState(
        mailbox_id="box1@rusprom.ru", provider="yandex",
        day_key=IN_WINDOW.strftime("%Y-%m-%d"), sent_today=0, sent_total=0,
        ramp_day=30, daily_limit=30, last_sent_at=None,
        paused=False, pause_reason=None))
    return sndr, store, suppression, opener, cid, sid


def _enqueue(store, cid, sid, rid, key="k1"):
    mid, _ = store.enqueue_message(MessageIn(
        idempotency_key=key, campaign_id=cid, recipient_id=rid,
        sequence_step_id=sid, scheduled_at=IN_WINDOW - timedelta(hours=1)))
    return mid


# --------------------------------------------------------------------------- #
# П1.1 — нормализация email/домена/ИНН
# --------------------------------------------------------------------------- #
def test_p11_upsert_normalizes_email_domain_inn(store):
    rid = store.upsert_recipient(RecipientIn(
        email="  USER@Site.RU ", domain="Site.RU", inn="77 07 083893"))
    r = store.get_recipient(rid)
    assert r.email == "user@site.ru"
    assert r.domain == "site.ru"
    assert r.inn == "7707083893"


def test_p11_upsert_dedups_case_variants(store):
    """USER@X и user@x — один получатель, а не два (уникальность по email)."""
    a = store.upsert_recipient(RecipientIn(email="User@X.ru", domain="X.ru"))
    b = store.upsert_recipient(RecipientIn(email="user@x.ru", domain="x.ru"))
    assert a == b


def test_p11_claim_skips_suppressed_raw_case_recipient(store, suppression):
    """Получатель, записанный в БД с верхним регистром (старые строки боевой
    БД), не должен проскочить NOT EXISTS-заслон claim_due_messages."""
    cid = store.create_campaign(CampaignIn(
        name="c", legal_entity="ООО «Руспром»", legal_inn="2221239841"))
    sid = store.add_step(SequenceStepIn(
        campaign_id=cid, step_index=0, delay_hours=0,
        subject_tmpl="s", body_tmpl="b"))
    # Сырая строка в обход upsert-нормализации — эмуляция старой БД.
    now = _now_iso()
    with store.transaction() as conn:
        conn.execute(
            "INSERT INTO recipients(email, domain, created_at, updated_at)"
            " VALUES (?,?,?,?)", ("USER@Site.RU", "Site.RU", now, now))
        rid = conn.execute("SELECT id FROM recipients WHERE email='USER@Site.RU'"
                           ).fetchone()["id"]
    _enqueue(store, cid, sid, rid)
    assert suppression.add_email("user@site.ru", "unsubscribe")

    claimed = store.claim_due_messages(
        now=datetime.now(UTC), mailbox_ids=["box1@rusprom.ru"], limit=10)
    assert claimed == []


def test_p11_query_recipients_suppressed_filter_matches_raw_case(store, suppression):
    now = _now_iso()
    with store.transaction() as conn:
        conn.execute(
            "INSERT INTO recipients(email, domain, created_at, updated_at)"
            " VALUES (?,?,?,?)", ("Boss@Firm.RU", "Firm.RU", now, now))
    assert suppression.add_domain("firm.ru", "competitor")
    got = store.query_recipients({"suppressed": True})
    assert [r.email for r in got] == ["Boss@Firm.RU"]
    assert store.query_recipients({"suppressed": False}) == []


# --------------------------------------------------------------------------- #
# П1.2 — отписка навсегда
# --------------------------------------------------------------------------- #
def test_p12_unsubscribe_upgrades_ttl_competitor_row(store, suppression):
    """Была competitor-запись с TTL → пришла отписка. Раньше DO NOTHING её
    игнорировал: TTL истекал и адрес снова «живой» вопреки отписке."""
    store.suppression_add(SuppressionIn(
        scope="email", value="a@b.ru", reason="competitor",
        expires_at=datetime.now(UTC) + timedelta(hours=1)))
    assert suppression.add_email("a@b.ru", "unsubscribe", source="one_click")
    entry = store.suppression_lookup(email="a@b.ru", domain="b.ru", inn=None)
    assert entry is not None
    assert entry.reason == "unsubscribe"
    assert entry.expires_at is None


def test_p12_unsubscribe_never_downgraded(store, suppression):
    suppression.add_email("a@b.ru", "unsubscribe")
    # Повторный импорт конкурентов НЕ понижает отписку до competitor-TTL.
    store.suppression_add(SuppressionIn(
        scope="email", value="a@b.ru", reason="competitor",
        expires_at=datetime.now(UTC) + timedelta(hours=1)))
    entry = store.suppression_lookup(email="a@b.ru", domain="b.ru", inn=None)
    assert entry.reason == "unsubscribe"
    assert entry.expires_at is None


def test_p12_unsubscribe_insert_ignores_expires_at(store):
    """Даже если вызывающий код передал TTL — отписка бессрочна."""
    store.suppression_add(SuppressionIn(
        scope="email", value="c@d.ru", reason="unsubscribe",
        expires_at=datetime.now(UTC) + timedelta(days=30)))
    entry = store.suppression_lookup(email="c@d.ru", domain="d.ru", inn=None)
    assert entry is not None and entry.expires_at is None


def test_p12_legacy_expired_unsubscribe_row_still_blocks(store, suppression):
    """Страховка для старых строк БД: unsubscribe с истёкшим expires_at всё
    равно активен — и в lookup, и в NOT EXISTS клейма."""
    past = _to_iso(datetime.now(UTC) - timedelta(days=1))
    now = _now_iso()
    with store.transaction() as conn:
        conn.execute(
            "INSERT INTO suppression(scope, value, reason, created_at, expires_at)"
            " VALUES ('email','old@x.ru','unsubscribe',?,?)", (now, past))
    entry = store.suppression_lookup(email="old@x.ru", domain="x.ru", inn=None)
    assert entry is not None and entry.reason == "unsubscribe"

    cid = store.create_campaign(CampaignIn(
        name="c", legal_entity="ООО «Руспром»", legal_inn="2221239841"))
    sid = store.add_step(SequenceStepIn(
        campaign_id=cid, step_index=0, delay_hours=0,
        subject_tmpl="s", body_tmpl="b"))
    rid = store.upsert_recipient(RecipientIn(email="old@x.ru", domain="x.ru"))
    _enqueue(store, cid, sid, rid)
    assert store.claim_due_messages(
        now=datetime.now(UTC), mailbox_ids=["box1@rusprom.ru"], limit=10) == []


def test_p12_is_suppressed_ignores_expiry_for_unsubscribe(store, suppression):
    past = _to_iso(datetime.now(UTC) - timedelta(days=1))
    now = _now_iso()
    with store.transaction() as conn:
        conn.execute(
            "INSERT INTO suppression(scope, value, reason, created_at, expires_at)"
            " VALUES ('email','old2@x.ru','unsubscribe',?,?)", (now, past))
    rid = store.upsert_recipient(RecipientIn(email="old2@x.ru", domain="x.ru"))
    entry = suppression.is_suppressed(store.get_recipient(rid))
    assert entry is not None and entry.reason == "unsubscribe"


def test_p12_suppression_remove_refuses_unsubscribe(store, suppression):
    suppression.add_email("no@more.ru", "unsubscribe")
    entry = store.suppression_lookup(email="no@more.ru", domain="more.ru", inn=None)
    with pytest.raises(ValidationError):
        store.suppression_remove(entry.id, reason="ошибка оператора")
    # Запись на месте.
    assert store.suppression_lookup(
        email="no@more.ru", domain="more.ru", inn=None) is not None
    # Competitor снимать по-прежнему можно.
    suppression.add_email("rival@corp.ru", "competitor")
    e2 = store.suppression_lookup(email="rival@corp.ru", domain="corp.ru", inn=None)
    assert store.suppression_remove(e2.id, reason="ошибочно внесён") is True


# --------------------------------------------------------------------------- #
# П1.4 — one-click честный статус
# --------------------------------------------------------------------------- #
@pytest.fixture
def server_url(config, store, suppression):
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    server = make_server(config, store, suppression, host="127.0.0.1", port=port)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    for _ in range(50):
        try:
            urlopen(f"http://127.0.0.1:{port}/health", timeout=0.1)
            break
        except Exception:
            _time.sleep(0.01)
    yield f"http://127.0.0.1:{port}"
    server.shutdown()
    server.server_close()
    thread.join(timeout=1)


def test_p14_one_click_missing_recipient_is_not_200(
        config, store, suppression, server_url):
    """Валидная подпись, но получателя нет в БД → провайдер должен увидеть
    ошибку, а не «Вы отписаны» (раньше — 200 при нулевом действии)."""
    unsub = Unsub(config, store, suppression)
    token = unsub.make_token(999999, 1)  # несуществующий rid
    req = Request(f"{server_url}/u?t={token}", method="POST",
                  data=b"List-Unsubscribe=One-Click")
    with pytest.raises(HTTPError) as exc:
        urlopen(req, timeout=2)
    assert exc.value.code == 404


def test_p14_one_click_success_still_200(config, store, suppression, server_url):
    unsub = Unsub(config, store, suppression)
    rid = store.upsert_recipient(RecipientIn(email="ok@x.ru", domain="x.ru"))
    token = unsub.make_token(rid, 1)
    resp = urlopen(Request(f"{server_url}/u?t={token}", method="POST",
                           data=b"List-Unsubscribe=One-Click"), timeout=2)
    assert resp.status == 200
    assert store.suppression_lookup(email="ok@x.ru", domain="x.ru", inn=None)


# --------------------------------------------------------------------------- #
# П1.5 — перепроверка has_reply прямо перед отправкой
# --------------------------------------------------------------------------- #
def test_p15_send_rechecks_reply_before_smtp(sender_env):
    """Ответ пришёл МЕЖДУ claim и send → followup не уходит."""
    sndr, store, _supp, opener, cid, sid = sender_env
    rid = store.upsert_recipient(RecipientIn(email="r@x.ru", domain="x.ru"))
    mid = _enqueue(store, cid, sid, rid)
    claimed = store.claim_due_messages(
        now=IN_WINDOW, mailbox_ids=["box1@rusprom.ru"], limit=1)
    assert [m.id for m in claimed] == [mid]

    # Ответ получателя фиксируется после claim, до send.
    store.append_event(EventIn(
        dedup_key=f"reply:{rid}", event_type="reply", event_ts=IN_WINDOW,
        recipient_id=rid, campaign_id=cid))

    rendered = RenderedMessage(subject="Тема", body="Тело")
    with pytest.raises(SuppressedError):
        sndr.send(claimed[0], rendered, "box1@rusprom.ru", now=IN_WINDOW)
    assert opener.sent == []  # SMTP не трогали
    assert store.get_message(mid).status == "skipped"


def test_p15_send_without_reply_goes_through(sender_env):
    sndr, store, _supp, opener, cid, sid = sender_env
    rid = store.upsert_recipient(RecipientIn(email="go@x.ru", domain="x.ru"))
    mid = _enqueue(store, cid, sid, rid)
    claimed = store.claim_due_messages(
        now=IN_WINDOW, mailbox_ids=["box1@rusprom.ru"], limit=1)
    result = sndr.send(claimed[0], RenderedMessage(subject="Т", body="Б"),
                       "box1@rusprom.ru", now=IN_WINDOW)
    assert result.ok
    assert len(opener.sent) == 1
    assert store.get_message(mid).status == "sent"


# --------------------------------------------------------------------------- #
# П1.6 — атрибуция: частичное совпадение не отменяет футер
# --------------------------------------------------------------------------- #
def test_p16_inn_only_in_body_still_gets_entity_footer():
    fields = {"legal_entity": "ООО «Руспром»", "legal_inn": "2221239841"}
    body = "Предложение по компрессорам. ИНН 2221239841."
    out = Personalizer._ensure_attribution(body, fields)
    assert "ООО «Руспром»" in out  # раньше футер молча пропускался


def test_p16_full_attribution_in_template_not_duplicated():
    fields = {"legal_entity": "ООО «Руспром»", "legal_inn": "2221239841"}
    body = "Оферта. ООО «Руспром», ИНН 2221239841."
    out = Personalizer._ensure_attribution(body, fields)
    assert out == body  # оба маркера на месте — футер не дублируем


# --------------------------------------------------------------------------- #
# БОНУС (сверх списка): токен и URL отписки в письме совместимы с сервером
# --------------------------------------------------------------------------- #
def test_bonus_sender_token_accepted_by_unsub_handler(
        config, store, suppression):
    """Токен, который sender кладёт в List-Unsubscribe, ОБЯЗАН приниматься
    Unsub.handle_one_click (раньше форматы были несовместимы)."""
    sndr = Sender(config, store, suppression, _Gates(), dry_run=True)
    rid = store.upsert_recipient(RecipientIn(email="link@x.ru", domain="x.ru"))
    cid = store.create_campaign(CampaignIn(
        name="c", legal_entity="ООО «Руспром»", legal_inn="2221239841"))
    token = sndr._make_unsub_token(rid, cid)

    unsub = Unsub(config, store, suppression)
    result = unsub.handle_one_click(token)
    assert result.ok and result.recipient_id == rid
    assert store.suppression_lookup(email="link@x.ru", domain="x.ru", inn=None)


def test_bonus_list_unsubscribe_url_uses_t_param(config, store, suppression):
    """URL в заголовке письма должен нести токен в параметре `t` — том самом,
    который читает unsub_server._parse_token (раньше писали `token=`).

    HTTP-вариант отписки с 27.07 выключен по умолчанию (эндпоинт не поднят),
    поэтому включаем его явно — проверяем именно формат URL, а не то, попадает
    ли он в заголовок.
    """
    config._data.setdefault("legal", {})["unsub_http_enabled"] = True
    sndr = Sender(config, store, suppression, _Gates(), dry_run=True)
    mb = config.mailboxes()[0]
    headers = sndr._list_unsubscribe_headers("abc.def", mb)
    url = headers["List-Unsubscribe"].split(",")[0].strip().strip("<>")
    params = parse_qs(urlparse(url).query)
    assert params.get("t") == ["abc.def"]
    assert "token" not in params
