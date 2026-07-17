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
