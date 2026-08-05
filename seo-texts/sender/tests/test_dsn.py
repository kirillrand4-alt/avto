# FILE: sender/tests/test_dsn.py
"""Разбор отбивок: кто отбился, почему и что с этим делает вотчер.

Материал — реальные отчёты: SecurityGateway (MDaemon) от el5-energo.ru
05.08.2026, постфиксовский «user unknown» и яндексовый 5.7.1. Проверяем ровно
то, из-за чего отбивки не работали: привязку к нашему письму и то, что отказ по
политике НЕ убивает живой адрес.
"""
from dataclasses import dataclass
from typing import Optional

from sender.dsn import parse_dsn
from sender.imap_watcher import EventIn, ImapWatcher, Recipient


# --- письма ---------------------------------------------------------------

# Отчёт шлюза получателя: расширенного кода нет вовсе, «500 Message rejected»
# в транскрипте, наше письмо приложено внутрь. Адрес в отчёте — ЧУЖОЙ
# (внутренняя пересылка в конторе получателя).
NDR_SECURITY_GATEWAY = b"""From: SecurityGateway for Email Servers <noreply@el5-energo.ru>
To: a.balakirev@compressor-store.ru
Subject: Permanent Delivery Failure
Content-Type: multipart/mixed; boundary="BOUND"
MIME-Version: 1.0

--BOUND
Content-Type: text/plain; charset="us-ascii"

SecurityGateway for Email Servers Non-Delivery Report

The attached message had PERMANENT fatal delivery errors!

YOUR MESSAGE WAS NOT DELIVERED TO ONE OR MORE RECIPIENTS!

Failed address: svetlana.rasskazova@el5-energo.ru

--- Session Transcript ---
Wed 2026-08-05 08:01:19: --> RCPT To:<svetlana.rasskazova@el5-energo.ru>
Wed 2026-08-05 08:01:19: <-- 250 2.1.5 Recipient OK
Wed 2026-08-05 08:01:19: --> DATA
Wed 2026-08-05 08:01:30: <-- 500 Message rejected
--- End Transcript ---

--BOUND
Content-Type: message/rfc822

From: a.balakirev@compressor-store.ru
To: maksim.karmazinenko@el5-energo.ru
Message-ID: <178590603105.5072.719@compressor-store.ru>
Subject: =?utf-8?b?0JLQvtC/0YDQvtGB?=

Text of the original letter.
--BOUND--
"""

NDR_POSTFIX_UNKNOWN = b"""From: MAILER-DAEMON@corp.example
To: a.balakirev@compressor-store.ru
Subject: Undelivered Mail Returned to Sender
Content-Type: multipart/report; report-type=delivery-status; boundary="B2"
MIME-Version: 1.0

--B2
Content-Type: text/plain; charset=us-ascii

<dead@corp.example>: host mx.corp.example said: 550 5.1.1 <dead@corp.example>:
    Recipient address rejected: User unknown in local recipient table

--B2
Content-Type: message/delivery-status

Final-Recipient: rfc822; dead@corp.example
Action: failed
Status: 5.1.1
Diagnostic-Code: smtp; 550 5.1.1 User unknown

--B2
Content-Type: message/rfc822

From: a.balakirev@compressor-store.ru
To: dead@corp.example
Message-ID: <orig-hard@compressor-store.ru>

body
--B2--
"""

NDR_POLICY_57 = b"""From: mailer-daemon@yandex.ru
To: a.balakirev@compressor-store.ru
Subject: Undeliverable
Content-Type: multipart/report; report-type=delivery-status; boundary="B3"
MIME-Version: 1.0

--B3
Content-Type: message/delivery-status

Final-Recipient: rfc822; live@corp.example
Action: failed
Status: 5.7.1
Diagnostic-Code: smtp; 550 5.7.1 Message rejected under suspicion of SPAM

--B3
Content-Type: message/rfc822

From: a.balakirev@compressor-store.ru
Message-ID: <orig-policy@compressor-store.ru>

body
--B3--
"""

NDR_SOFT_QUOTA = b"""From: postmaster@corp.example
To: a.balakirev@compressor-store.ru
Subject: Delivery Status Notification (Delay)
Content-Type: multipart/report; report-type=delivery-status; boundary="B4"
MIME-Version: 1.0

--B4
Content-Type: message/delivery-status

Final-Recipient: rfc822; full@corp.example
Action: delayed
Status: 4.2.2
Diagnostic-Code: smtp; 452 4.2.2 Mailbox full

--B4--
"""


# --- моки -----------------------------------------------------------------

@dataclass
class MockMailboxCfg:
    mailbox_id: str = "a.balakirev@compressor-store.ru"
    provider: str = "mailru"
    smtp_host: str = "smtp.mail.ru"
    smtp_port: int = 465
    imap_host: str = "imap.mail.ru"
    imap_port: int = 993
    login: str = "a.balakirev@compressor-store.ru"
    password_env: str = "PW"
    from_name: str = "Антон"
    signature: Optional[str] = None
    pool: Optional[str] = None
    is_warmup_node: bool = False


@dataclass
class MockMessage:
    id: int
    recipient_id: int
    campaign_id: int
    rfc_message_id: str


class MockConfig:
    def mailboxes(self):
        return [MockMailboxCfg()]

    def get(self, key, default=None):
        return {"imap.batch": 50, "imap.auto_suppress_on_bounce": True,
                "imap.auto_suppress_on_complaint": True,
                "imap.soft_bounce_max_retries": 0}.get(key, default)


class MockStore:
    def __init__(self):
        self.messages: dict = {}
        self.recipients: dict = {}
        self.by_email: dict = {}
        self.aliases: dict = {}
        self.events: list = []

    def find_message_by_rfc_id(self, rfc_message_id: str):
        return self.messages.get(rfc_message_id)

    def get_recipient(self, recipient_id: int):
        return self.recipients.get(recipient_id)

    def find_recipient_by_email(self, email: str):
        r = self.by_email.get((email or "").lower())
        return {"id": r.id, "email": r.email} if r else None

    def delivery_emails_for_recipient(self, recipient_id: int, *, limit: int = 20):
        return self.aliases.get(recipient_id, [])

    def append_event(self, e: EventIn):
        for i, ex in enumerate(self.events):
            if ex.dedup_key == e.dedup_key:
                return i, False
        self.events.append(e)
        return len(self.events) - 1, True

    def transaction(self):
        return self

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class MockSuppression:
    def __init__(self):
        self.suppressed: list = []

    def add_email(self, email, reason, *, source="", campaign_id=None):
        self.suppressed.append((email, reason))
        return True


def _recipient(rid: int, email: str) -> Recipient:
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    return Recipient(id=rid, email=email, domain=email.split("@")[1], inn=None,
                     company_name="ООО Тест", okved=None, segment=None,
                     bitrix_id=None, contact_name=None, mx_provider="other",
                     valid_status="valid", catch_all=None, role_based=False,
                     disposable=False, source=None, extra={},
                     created_at=now, updated_at=now)


def _watcher(store, suppression):
    return ImapWatcher(MockConfig(), store, suppression)


# --- разбор ---------------------------------------------------------------

def test_gateway_ndr_bez_koda_razobran():
    """Отчёт без 5.x.x: адрес вынут, вердикт — политика, а не мёртвый ящик."""
    info = parse_dsn(NDR_SECURITY_GATEWAY)
    assert info.failed == ["svetlana.rasskazova@el5-energo.ru"]
    assert info.smtp_code == 500
    assert info.verdict == "policy"
    assert info.orig_message_id == "<178590603105.5072.719@compressor-store.ru>"


def test_permanent_fatal_ne_delaet_hard():
    """«PERMANENT fatal delivery errors» — боилерплейт MDaemon, не приговор ящику."""
    assert parse_dsn(NDR_SECURITY_GATEWAY).verdict != "hard"


def test_postfix_user_unknown_hard():
    info = parse_dsn(NDR_POSTFIX_UNKNOWN)
    assert info.verdict == "hard"
    assert info.status == "5.1.1"
    assert info.failed == ["dead@corp.example"]


def test_57_eto_politika():
    info = parse_dsn(NDR_POLICY_57)
    assert info.verdict == "policy" and info.status == "5.7.1"


def test_perepolnen_yashchik_soft():
    info = parse_dsn(NDR_SOFT_QUOTA)
    assert info.verdict == "soft"
    assert info.failed == ["full@corp.example"]


def test_sluzhebnye_adresa_ne_schitayutsya_poluchatelyami():
    """postmaster@/mailer-daemon@ из шапки отчёта в failed попадать не должны."""
    for raw in (NDR_SECURITY_GATEWAY, NDR_POSTFIX_UNKNOWN, NDR_SOFT_QUOTA):
        assert not any(a.split("@")[0] in ("postmaster", "mailer-daemon", "noreply")
                       for a in parse_dsn(raw).failed)


NDR_HTML = b"""From: SecurityGateway <noreply@el5-energo.ru>
To: a.balakirev@compressor-store.ru
Subject: Permanent Delivery Failure
Content-Type: text/html; charset="utf-8"
MIME-Version: 1.0

<html><body><pre>
Failed address: svetlana.rasskazova@el5-energo.ru<br>
--- Session Transcript ---<br>
Wed 2026-08-05 08:01:30: &lt;-- 500 Message rejected<br>
</pre></body></html>
"""


def test_html_otchet_razbiraetsya():
    """Шлюз прислал отчёт HTML-ом: снимаем разметку и &lt;, иначе кода не видно."""
    info = parse_dsn(NDR_HTML)
    assert info.failed == ["svetlana.rasskazova@el5-energo.ru"]
    assert info.smtp_code == 500
    assert info.verdict == "policy"


def test_bityi_otchet_ne_ronyaet_razbor():
    assert parse_dsn(b"\xff\xfe not a message at all").verdict == "unknown"


# --- поведение вотчера ----------------------------------------------------

def test_privyazka_cherez_vlozhennyi_original():
    """У NDR нет In-Reply-To — письмо ищется по Message-ID вложенного оригинала."""
    store = MockStore()
    store.recipients[1] = _recipient(1, "maksim.karmazinenko@el5-energo.ru")
    store.messages["<178590603105.5072.719@compressor-store.ru>"] = MockMessage(
        id=10, recipient_id=1, campaign_id=5,
        rfc_message_id="<178590603105.5072.719@compressor-store.ru>")
    ev = _watcher(store, MockSuppression()).classify(NDR_SECURITY_GATEWAY)
    assert ev.kind == "dsn"
    assert ev.recipient_id == 1


def test_privyazka_po_adresu_iz_otcheta():
    """Оригинал не вернули — получателя находим по адресу из отчёта."""
    store = MockStore()
    r = _recipient(7, "dead@corp.example")
    store.recipients[7] = r
    store.by_email["dead@corp.example"] = r
    ev = _watcher(store, MockSuppression()).classify(NDR_POSTFIX_UNKNOWN)
    assert ev.recipient_id == 7


def test_politika_ne_suppressit_zhivoy_adres():
    """5.7.1 — письмо не понравилось фильтру, ящик жив: стоп-лист не трогаем."""
    store = MockStore()
    r = _recipient(2, "live@corp.example")
    store.recipients[2] = r
    store.by_email["live@corp.example"] = r
    store.messages["<orig-policy@compressor-store.ru>"] = MockMessage(
        id=11, recipient_id=2, campaign_id=5,
        rfc_message_id="<orig-policy@compressor-store.ru>")
    supp = MockSuppression()
    w = _watcher(store, supp)
    ev = w.classify(NDR_POLICY_57)
    w._process_event(ev, "a.balakirev@compressor-store.ru")
    assert supp.suppressed == []
    # но событие для гейтов записано, и в нём видна причина
    bounce = [e for e in store.events if e.event_type == "bounce"]
    assert len(bounce) == 1
    assert bounce[0].detail["dsn"]["verdict"] == "policy"


def test_chuzhoy_adres_v_otchete_ne_ubivaet_nashego_poluchatelya():
    """Письмо переслали внутри конторы и оно упало там — наш адрес живой."""
    store = MockStore()
    store.recipients[1] = _recipient(1, "maksim.karmazinenko@el5-energo.ru")
    store.messages["<178590603105.5072.719@compressor-store.ru>"] = MockMessage(
        id=10, recipient_id=1, campaign_id=5,
        rfc_message_id="<178590603105.5072.719@compressor-store.ru>")
    supp = MockSuppression()
    w = _watcher(store, supp)
    ev = w.classify(NDR_SECURITY_GATEWAY)
    # даже если бы вердикт был жёстким — адрес не наш, гасить нечего
    ev = type(ev)(**{**ev.__dict__, "dsn": {**ev.dsn, "verdict": "hard"}})
    w._process_event(ev, "a.balakirev@compressor-store.ru")
    assert supp.suppressed == []


def test_hard_gasit_imenno_otbivshiysya_adres():
    """Оператор вписал контакт руками, отбился он — база остаётся жить."""
    store = MockStore()
    r = _recipient(3, "info@corp.example")
    store.recipients[3] = r
    store.aliases[3] = ["dead@corp.example"]
    store.messages["<orig-hard@compressor-store.ru>"] = MockMessage(
        id=12, recipient_id=3, campaign_id=5,
        rfc_message_id="<orig-hard@compressor-store.ru>")
    supp = MockSuppression()
    w = _watcher(store, supp)
    ev = w.classify(NDR_POSTFIX_UNKNOWN)
    w._process_event(ev, "a.balakirev@compressor-store.ru")
    assert supp.suppressed == [("dead@corp.example", "bounce_hard")]


def test_otchet_bez_adresa_gasit_bazu_i_aliasy():
    """Адрес в отчёте не назван — поведение как раньше: базовый плюс алиасы."""
    store = MockStore()
    r = _recipient(4, "base@corp.example")
    store.recipients[4] = r
    store.aliases[4] = ["alias@corp.example"]
    supp = MockSuppression()
    w = _watcher(store, supp)
    from sender.imap_watcher import InboundEvent
    ev = InboundEvent(kind="dsn", mailbox_id="a.balakirev@compressor-store.ru",
                      dedup_key="imap:1:1:dsn", rfc_message_id=None,
                      from_addr="postmaster@corp.example", thread_id=None,
                      recipient_id=4, snippet="5.1.1 no such user",
                      raw_headers={"Status": "5.1.1"})
    w._process_event(ev, "a.balakirev@compressor-store.ru")
    assert sorted(a for a, _ in supp.suppressed) == [
        "alias@corp.example", "base@corp.example"]
