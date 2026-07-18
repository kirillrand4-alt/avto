# FILE: sender/tests/test_imap_watcher.py
import pytest
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional
from unittest.mock import Mock, MagicMock
from sender.imap_watcher import ImapWatcher, InboundEvent, EventIn, Recipient

@dataclass
class MockMessage:
    id: int
    recipient_id: int
    campaign_id: int
    rfc_message_id: str

@dataclass
class MockMailboxCfg:
    mailbox_id: str
    provider: str
    smtp_host: str = "smtp.example.com"
    smtp_port: int = 465
    imap_host: str = "imap.example.com"
    imap_port: int = 993
    login: str = "test@example.com"
    password_env: str = "TEST_PASSWORD"
    from_name: str = "Test Sender"
    signature: Optional[str] = None
    pool: Optional[str] = None
    is_warmup_node: bool = False

class MockConfig:
    def mailboxes(self):
        return [MockMailboxCfg(mailbox_id="test@example.com", provider="yandex")]
    
    def get(self, key, default=None):
        return {"imap.batch": 50, "imap.auto_suppress_on_bounce": True, "imap.auto_suppress_on_complaint": True}.get(key, default)

class MockStore:
    def __init__(self):
        self.messages = {}
        self.recipients = {}
        self.events = []
        self.transaction_active = False
    
    def find_message_by_rfc_id(self, rfc_message_id: str):
        return self.messages.get(rfc_message_id)
    
    def get_recipient(self, recipient_id: int):
        return self.recipients.get(recipient_id)
    
    def append_event(self, e: EventIn):
        for i, existing in enumerate(self.events):
            if existing.dedup_key == e.dedup_key:
                return i, False
        self.events.append(e)
        return len(self.events) - 1, True
    
    def transaction(self):
        return self
    
    def __enter__(self):
        self.transaction_active = True
        return self
    
    def __exit__(self, *args):
        self.transaction_active = False

class MockSuppression:
    def __init__(self):
        self.suppressed = []
    
    def add_email(self, email: str, reason: str, *, source: str = "", campaign_id: Optional[int] = None):
        self.suppressed.append((email, reason, source, campaign_id))
        return True

class MockReplyDesk:
    def __init__(self):
        self.warm_leads = []
    
    def push_warm_lead(self, recipient: Recipient, thread_id: str, snippet: str):
        self.warm_leads.append((recipient.email, thread_id, snippet))

def test_classify_reply():
    config = MockConfig()
    store = MockStore()
    suppression = MockSuppression()
    watcher = ImapWatcher(config, store, suppression)
    
    raw = b"""From: user@example.com
To: test@example.com
Subject: Re: Test
In-Reply-To: <original@msg.id>
References: <original@msg.id>

This is a reply message.
"""
    
    event = watcher.classify(raw)
    assert event.kind == "reply"
    assert event.from_addr == "user@example.com"
    assert event.rfc_message_id == "<original@msg.id>"
    assert "This is a reply message." in event.snippet

def test_classify_dsn_hard_bounce():
    config = MockConfig()
    store = MockStore()
    suppression = MockSuppression()
    watcher = ImapWatcher(config, store, suppression)
    
    raw = b"""From: postmaster@example.com
To: test@example.com
Subject: Delivery Status Notification (Failure)
Status: 5.1.1

The following message could not be delivered. Permanent failure.
"""
    
    event = watcher.classify(raw)
    assert event.kind == "dsn"
    assert "5.1.1" in event.snippet or "5.1.1" in event.raw_headers.get("Status", "")

def test_classify_dsn_soft_bounce():
    config = MockConfig()
    store = MockStore()
    suppression = MockSuppression()
    watcher = ImapWatcher(config, store, suppression)
    
    raw = b"""From: postmaster@example.com
To: test@example.com
Subject: Delivery Status Notification (Delay)
Status: 4.2.1

Temporary failure. Will retry.
"""
    
    event = watcher.classify(raw)
    assert event.kind == "dsn"

def test_classify_complaint():
    config = MockConfig()
    store = MockStore()
    suppression = MockSuppression()
    watcher = ImapWatcher(config, store, suppression)
    
    raw = b"""From: abuse@example.com
To: test@example.com
Subject: Abuse Report
Content-Type: message/feedback-report

This is a spam complaint.
"""
    
    event = watcher.classify(raw)
    assert event.kind == "complaint"

def test_dedup_by_uid():
    config = MockConfig()
    store = MockStore()
    suppression = MockSuppression()
    watcher = ImapWatcher(config, store, suppression)
    
    event1 = InboundEvent(
        kind="reply",
        mailbox_id="test@example.com",
        dedup_key="imap:123:456:reply",
        rfc_message_id="<test@msg>",
        from_addr="user@example.com",
        thread_id="thread1",
        recipient_id=1,
        snippet="Test",
        raw_headers={}
    )
    
    watcher._process_event(event1, "test@example.com")
    assert len(store.events) == 1
    
    watcher._process_event(event1, "test@example.com")
    assert len(store.events) == 1

def test_hard_bounce_suppression():
    config = MockConfig()
    store = MockStore()
    suppression = MockSuppression()
    watcher = ImapWatcher(config, store, suppression)
    
    recipient = Recipient(
        id=1, email="bounce@example.com", domain="example.com",
        inn=None, company_name=None, okved=None, segment=None,
        bitrix_id=None, contact_name=None, mx_provider="yandex",
        valid_status="valid", catch_all=None, role_based=None,
        disposable=None, source=None, extra={},
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc)
    )
    store.recipients[1] = recipient
    store.messages["<original@msg>"] = MockMessage(
        id=10, recipient_id=1, campaign_id=5, rfc_message_id="<original@msg>"
    )
    
    event = InboundEvent(
        kind="dsn",
        mailbox_id="test@example.com",
        dedup_key="imap:123:789:dsn",
        rfc_message_id="<original@msg>",
        from_addr="postmaster@example.com",
        thread_id=None,
        recipient_id=1,
        snippet="5.1.1 permanent failure",
        raw_headers={"Status": "5.1.1"}
    )
    
    watcher._process_event(event, "test@example.com")
    assert len(suppression.suppressed) == 1
    assert suppression.suppressed[0][0] == "bounce@example.com"
    assert suppression.suppressed[0][1] == "bounce_hard"

def test_reply_stops_chain():
    config = MockConfig()
    store = MockStore()
    suppression = MockSuppression()
    reply_desk = MockReplyDesk()
    watcher = ImapWatcher(config, store, suppression, reply_desk)
    
    recipient = Recipient(
        id=2, email="reply@example.com", domain="example.com",
        inn=None, company_name=None, okved=None, segment=None,
        bitrix_id=None, contact_name=None, mx_provider="yandex",
        valid_status="valid", catch_all=None, role_based=None,
        disposable=None, source=None, extra={},
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc)
    )
    store.recipients[2] = recipient
    store.messages["<original@msg2>"] = MockMessage(
        id=20, recipient_id=2, campaign_id=6, rfc_message_id="<original@msg2>"
    )
    
    event = InboundEvent(
        kind="reply",
        mailbox_id="test@example.com",
        dedup_key="imap:123:999:reply",
        rfc_message_id="<original@msg2>",
        from_addr="reply@example.com",
        thread_id="thread2",
        recipient_id=2,
        snippet="Thanks for the info!",
        raw_headers={}
    )
    
    watcher._process_event(event, "test@example.com")
    
    skip_events = [e for e in store.events if e.event_type == "skip"]
    assert len(skip_events) == 1
    assert skip_events[0].recipient_id == 2
    
    assert len(reply_desk.warm_leads) == 1
    assert reply_desk.warm_leads[0][0] == "reply@example.com"
    assert reply_desk.warm_leads[0][1] == "thread2"

def test_complaint_suppression():
    config = MockConfig()
    store = MockStore()
    suppression = MockSuppression()
    watcher = ImapWatcher(config, store, suppression)
    
    recipient = Recipient(
        id=3, email="complaint@example.com", domain="example.com",
        inn=None, company_name=None, okved=None, segment=None,
        bitrix_id=None, contact_name=None, mx_provider="yandex",
        valid_status="valid", catch_all=None, role_based=None,
        disposable=None, source=None, extra={},
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc)
    )
    store.recipients[3] = recipient
    store.messages["<original@msg3>"] = MockMessage(
        id=30, recipient_id=3, campaign_id=7, rfc_message_id="<original@msg3>"
    )
    
    event = InboundEvent(
        kind="complaint",
        mailbox_id="test@example.com",
        dedup_key="imap:123:1001:complaint",
        rfc_message_id="<original@msg3>",
        from_addr="abuse@example.com",
        thread_id=None,
        recipient_id=3,
        snippet="spam complaint",
        raw_headers={}
    )
    
    watcher._process_event(event, "test@example.com")
    assert len(suppression.suppressed) == 1
    assert suppression.suppressed[0][0] == "complaint@example.com"
    assert suppression.suppressed[0][1] == "complaint"

def test_thread_id_extraction():
    config = MockConfig()
    store = MockStore()
    suppression = MockSuppression()
    watcher = ImapWatcher(config, store, suppression)
    
    raw = b"""From: user@example.com
To: test@example.com
Subject: Re: Test
In-Reply-To: <abc123@msg.id>

Reply body.
"""
    
    event = watcher.classify(raw)
    assert event.thread_id is not None
    assert len(event.thread_id) == 16

# ---- Greylist/soft-bounce ретрай (imap.soft_bounce_*) ----

@dataclass
class MockFullMessage:
    """Message-строка с полями, нужными ретраю (idempotency_key и др.)."""
    id: int
    recipient_id: int
    campaign_id: int
    rfc_message_id: str
    idempotency_key: str = "c5:r1:s1"
    sequence_step_id: int = 1
    thread_id: Optional[str] = None
    in_reply_to: Optional[str] = None

class RetryMockStore(MockStore):
    def __init__(self, replied=False):
        super().__init__()
        self.enqueued = []
        self.replied = replied

    def enqueue_message(self, m):
        for i, ex in enumerate(self.enqueued):
            if ex.idempotency_key == m.idempotency_key:
                return i, False
        self.enqueued.append(m)
        return len(self.enqueued) - 1, True

    def has_reply(self, recipient_id, campaign_id):
        return self.replied

def _mk_recipient(rid, email_addr):
    return Recipient(
        id=rid, email=email_addr, domain=email_addr.split("@")[1],
        inn=None, company_name=None, okved=None, segment=None,
        bitrix_id=None, contact_name=None, mx_provider="yandex",
        valid_status="valid", catch_all=None, role_based=None,
        disposable=None, source=None, extra={},
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc))

def _soft_dsn_event(dedup="imap:1:1:dsn", rfc="<soft@msg>"):
    return InboundEvent(
        kind="dsn", mailbox_id="test@example.com", dedup_key=dedup,
        rfc_message_id=rfc, from_addr="postmaster@example.com",
        thread_id=None, recipient_id=1,
        snippet="4.2.0 greylisted, try again later",
        raw_headers={"Status": "4.2.0"})

def test_soft_bounce_schedules_retry():
    """4.x.x → новый message :sbr1 с отложенным scheduled_at + событие retry_scheduled."""
    store = RetryMockStore()
    store.recipients[1] = _mk_recipient(1, "grey@example.com")
    store.messages["<soft@msg>"] = MockFullMessage(
        id=10, recipient_id=1, campaign_id=5, rfc_message_id="<soft@msg>",
        idempotency_key="c5:r1:s1", thread_id="t1", in_reply_to="<seed@msg>")
    watcher = ImapWatcher(MockConfig(), store, MockSuppression())

    before = datetime.now(timezone.utc)
    watcher._process_event(_soft_dsn_event(), "test@example.com")

    assert len(store.enqueued) == 1
    retry = store.enqueued[0]
    assert retry.idempotency_key == "c5:r1:s1:sbr1"
    assert retry.campaign_id == 5 and retry.recipient_id == 1
    assert retry.sequence_step_id == 1
    assert retry.thread_id == "t1" and retry.in_reply_to == "<seed@msg>"
    # дефолт 45 мин: не раньше +44 и не позже +46
    delta_min = (retry.scheduled_at - before).total_seconds() / 60
    assert 44 <= delta_min <= 46
    # никакого suppress
    assert store.recipients[1].email not in [s[0] for s in []]
    retry_events = [e for e in store.events if e.event_type == "retry_scheduled"]
    assert len(retry_events) == 1
    assert retry_events[0].detail["depth"] == 1

def test_soft_bounce_retry_of_retry_increments_depth():
    """DSN на письмо :sbr1 → планируется :sbr2 (глубина растёт, задержка длиннее)."""
    store = RetryMockStore()
    store.recipients[1] = _mk_recipient(1, "grey@example.com")
    store.messages["<soft@msg>"] = MockFullMessage(
        id=11, recipient_id=1, campaign_id=5, rfc_message_id="<soft@msg>",
        idempotency_key="c5:r1:s1:sbr1")
    watcher = ImapWatcher(MockConfig(), store, MockSuppression())

    before = datetime.now(timezone.utc)
    watcher._process_event(_soft_dsn_event(), "test@example.com")

    assert [m.idempotency_key for m in store.enqueued] == ["c5:r1:s1:sbr2"]
    delta_min = (store.enqueued[0].scheduled_at - before).total_seconds() / 60
    assert 88 <= delta_min <= 92  # 45 * 2

def test_soft_bounce_respects_max_retries():
    """Глубина == потолку (2) → больше не ретраим."""
    store = RetryMockStore()
    store.recipients[1] = _mk_recipient(1, "grey@example.com")
    store.messages["<soft@msg>"] = MockFullMessage(
        id=12, recipient_id=1, campaign_id=5, rfc_message_id="<soft@msg>",
        idempotency_key="c5:r1:s1:sbr2")
    watcher = ImapWatcher(MockConfig(), store, MockSuppression())
    watcher._process_event(_soft_dsn_event(), "test@example.com")
    assert store.enqueued == []

def test_soft_bounce_no_retry_after_reply():
    """Получатель уже ответил → цепочку не продолжаем (стоп-на-ответ)."""
    store = RetryMockStore(replied=True)
    store.recipients[1] = _mk_recipient(1, "grey@example.com")
    store.messages["<soft@msg>"] = MockFullMessage(
        id=13, recipient_id=1, campaign_id=5, rfc_message_id="<soft@msg>")
    watcher = ImapWatcher(MockConfig(), store, MockSuppression())
    watcher._process_event(_soft_dsn_event(), "test@example.com")
    assert store.enqueued == []

def test_hard_bounce_does_not_retry():
    """5.x.x → suppress (как раньше), ретрая нет."""
    store = RetryMockStore()
    store.recipients[1] = _mk_recipient(1, "dead@example.com")
    store.messages["<hard@msg>"] = MockFullMessage(
        id=14, recipient_id=1, campaign_id=5, rfc_message_id="<hard@msg>")
    suppression = MockSuppression()
    watcher = ImapWatcher(MockConfig(), store, suppression)
    ev = InboundEvent(
        kind="dsn", mailbox_id="test@example.com", dedup_key="imap:1:2:dsn",
        rfc_message_id="<hard@msg>", from_addr="postmaster@example.com",
        thread_id=None, recipient_id=1,
        snippet="5.1.1 no such user", raw_headers={"Status": "5.1.1"})
    watcher._process_event(ev, "test@example.com")
    assert store.enqueued == []
    assert [s[1] for s in suppression.suppressed] == ["bounce_hard"]

def test_unparseable_dsn_no_retry():
    """DSN без явного 4.x.x/5.x.x кода — не suppress и не ретрай (как раньше)."""
    store = RetryMockStore()
    store.recipients[1] = _mk_recipient(1, "odd@example.com")
    store.messages["<odd@msg>"] = MockFullMessage(
        id=15, recipient_id=1, campaign_id=5, rfc_message_id="<odd@msg>")
    suppression = MockSuppression()
    watcher = ImapWatcher(MockConfig(), store, suppression)
    ev = InboundEvent(
        kind="dsn", mailbox_id="test@example.com", dedup_key="imap:1:3:dsn",
        rfc_message_id="<odd@msg>", from_addr="postmaster@example.com",
        thread_id=None, recipient_id=1,
        snippet="mail delivery failed for unclear reasons", raw_headers={})
    watcher._process_event(ev, "test@example.com")
    assert store.enqueued == [] and suppression.suppressed == []

def test_soft_retry_idempotent_double_dsn():
    """Два разных DSN-события на одно письмо → один retry (ON CONFLICT-семантика)."""
    store = RetryMockStore()
    store.recipients[1] = _mk_recipient(1, "grey@example.com")
    store.messages["<soft@msg>"] = MockFullMessage(
        id=16, recipient_id=1, campaign_id=5, rfc_message_id="<soft@msg>")
    watcher = ImapWatcher(MockConfig(), store, MockSuppression())
    watcher._process_event(_soft_dsn_event(dedup="imap:1:4:dsn"), "test@example.com")
    watcher._process_event(_soft_dsn_event(dedup="imap:1:5:dsn"), "test@example.com")
    assert len(store.enqueued) == 1

def test_soft_retry_disabled_by_config():
    """imap.soft_bounce_max_retries=0 → поведение как раньше (ничего не планируем)."""
    class NoRetryConfig(MockConfig):
        def get(self, key, default=None):
            if key == "imap.soft_bounce_max_retries":
                return 0
            return super().get(key, default)
    store = RetryMockStore()
    store.recipients[1] = _mk_recipient(1, "grey@example.com")
    store.messages["<soft@msg>"] = MockFullMessage(
        id=17, recipient_id=1, campaign_id=5, rfc_message_id="<soft@msg>")
    watcher = ImapWatcher(NoRetryConfig(), store, MockSuppression())
    watcher._process_event(_soft_dsn_event(), "test@example.com")
    assert store.enqueued == []

# ---- Вайринг суб-классификации ответов (reply_classify) ----

def _reply_event(snippet, dedup="imap:9:1:reply", rfc="<orig@msg>", headers=None):
    return InboundEvent(
        kind="reply", mailbox_id="test@example.com", dedup_key=dedup,
        rfc_message_id=rfc, from_addr="user@example.com",
        thread_id="t-sub", recipient_id=1, snippet=snippet,
        raw_headers=headers or {"Subject": "Re: Оборудование"})

def _wired(store):
    store.recipients[1] = _mk_recipient(1, "user@corp.example")
    store.messages["<orig@msg>"] = MockFullMessage(
        id=50, recipient_id=1, campaign_id=9, rfc_message_id="<orig@msg>")
    desk = MockReplyDesk()
    suppression = MockSuppression()
    return ImapWatcher(MockConfig(), store, suppression, desk), desk, suppression

def test_autoreply_does_not_stop_chain():
    """OOO-автоответ: событие reply_auto (цепочка живёт), лида и skip нет."""
    store = RetryMockStore()
    watcher, desk, _ = _wired(store)
    watcher._process_event(
        _reply_event("Я в отпуске до 25.07, по срочным вопросам звоните коллеге"),
        "test@example.com")
    assert [e.event_type for e in store.events] == ["reply_auto"]
    assert desk.warm_leads == []

def test_reply_text_unsubscribe_suppresses():
    """«Отпишите меня» текстом = suppression + не лид (цепочка стоит по reply)."""
    store = RetryMockStore()
    watcher, desk, suppression = _wired(store)
    watcher._process_event(
        _reply_event("Отпишите меня от рассылки, пожалуйста"), "test@example.com")
    assert [s[1] for s in suppression.suppressed] == ["unsubscribe"]
    assert suppression.suppressed[0][2] == "reply_text"
    assert desk.warm_leads == []
    assert any(e.event_type == "reply" for e in store.events)

def test_not_interested_stops_without_lead():
    store = RetryMockStore()
    watcher, desk, suppression = _wired(store)
    watcher._process_event(
        _reply_event("Спасибо, неактуально: есть поставщик"), "test@example.com")
    assert desk.warm_leads == []
    assert suppression.suppressed == []  # отказ != отписка
    assert any(e.event_type == "skip" for e in store.events)  # стоп цепочки

def test_hot_reply_lead_prefixed_with_kind_and_phone():
    store = RetryMockStore()
    watcher, desk, _ = _wired(store)
    watcher._process_event(
        _reply_event("Пришлите КП и прайс. Тел +7 (912) 345-67-89"),
        "test@example.com")
    assert len(desk.warm_leads) == 1
    snippet = desk.warm_leads[0][2]
    assert snippet.startswith("[hot, тел +79123456789]")
    # телефон и kind ушли и в detail события
    ev = [e for e in store.events if e.event_type == "reply"][0]
    assert ev.detail["reply_kind"] == "hot"
    assert ev.detail["phone"] == "+79123456789"
