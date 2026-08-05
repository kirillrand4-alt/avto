"""
Tests for sender/unsub.py: token generation, signature verification,
List-Unsubscribe headers, one-click handler, and safety invariants.
"""

import base64
import hashlib
import hmac
import json
import os
import sqlite3
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

import pytest


from sender.unsub import ValidationError


@pytest.fixture
def temp_db():
    """Create temporary SQLite database with schema."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA foreign_keys=ON")
    
    # Minimal schema for unsub tests
    conn.executescript("""
        CREATE TABLE recipients (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT NOT NULL UNIQUE,
            domain TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        
        CREATE TABLE suppression (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            scope TEXT NOT NULL,
            value TEXT NOT NULL,
            reason TEXT NOT NULL,
            source TEXT,
            campaign_id INTEGER,
            created_at TEXT NOT NULL,
            expires_at TEXT
        );
        CREATE UNIQUE INDEX ux_suppression_scope_val ON suppression(scope, value);
    """)
    conn.commit()
    
    yield path
    
    conn.close()
    Path(path).unlink(missing_ok=True)


@pytest.fixture
def mock_config():
    """Mock Config with legal settings."""
    class LegalCfg:
        unsub_base_url = "https://example.com/u"
        unsub_secret_env = "TEST_UNSUB_SECRET"
        entity = "ООО Руспром"
    
    class MockConfig:
        def legal(self):
            return LegalCfg()
    
    os.environ["TEST_UNSUB_SECRET"] = "test-secret-key-32-bytes-long!!"
    yield MockConfig()
    del os.environ["TEST_UNSUB_SECRET"]


@pytest.fixture
def mock_store(temp_db):
    """Mock Store with recipient and suppression operations."""
    class Recipient:
        def __init__(self, id, email, domain):
            self.id = id
            self.email = email
            self.domain = domain
    
    class MockStore:
        def __init__(self, db_path):
            self.conn = sqlite3.connect(db_path)
            self.conn.row_factory = sqlite3.Row
        
        def get_recipient(self, recipient_id):
            cur = self.conn.execute(
                "SELECT id, email, domain FROM recipients WHERE id=?",
                (recipient_id,)
            )
            row = cur.fetchone()
            if not row:
                return None
            return Recipient(row["id"], row["email"], row["domain"])
        
        def add_recipient(self, email, domain):
            now = datetime.now(timezone.utc).isoformat()
            cur = self.conn.execute(
                "INSERT INTO recipients (email, domain, created_at, updated_at) VALUES (?, ?, ?, ?)",
                (email, domain, now, now)
            )
            self.conn.commit()
            return cur.lastrowid
        
        def suppression_add(self, scope, value, reason, source="", campaign_id=None):
            now = datetime.now(timezone.utc).isoformat()
            try:
                self.conn.execute(
                    "INSERT INTO suppression (scope, value, reason, source, campaign_id, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                    (scope, value, reason, source, campaign_id, now)
                )
                self.conn.commit()
                return True
            except sqlite3.IntegrityError:
                return False
        
        def suppression_exists(self, scope, value):
            cur = self.conn.execute(
                "SELECT 1 FROM suppression WHERE scope=? AND value=? LIMIT 1",
                (scope, value)
            )
            return cur.fetchone() is not None
        
        def close(self):
            self.conn.close()
    
    store = MockStore(temp_db)
    yield store
    store.close()


@pytest.fixture
def mock_suppression(mock_store):
    """Mock Suppression with add_email method."""
    class MockSuppression:
        def __init__(self, store):
            self._store = store
        
        def add_email(self, email, reason, source="", campaign_id=None):
            return self._store.suppression_add("email", email, reason, source, campaign_id)
    
    return MockSuppression(mock_store)


@pytest.fixture
def unsub_instance(mock_config, mock_store, mock_suppression):
    """Create Unsub instance with mocks."""
    from sender.unsub import Unsub
    return Unsub(mock_config, mock_store, mock_suppression)


# ---- Happy Path Tests ----

def test_make_token_valid_format(unsub_instance):
    """Token should be valid base64url with dot separator."""
    token = unsub_instance.make_token(recipient_id=123, campaign_id=456)
    
    assert isinstance(token, str)
    assert "." in token
    
    parts = token.split(".")
    assert len(parts) == 2
    
    # Both parts should be valid base64url
    for part in parts:
        padding = (4 - len(part) % 4) % 4
        part_padded = part + "=" * padding
        decoded = base64.urlsafe_b64decode(part_padded.encode("ascii"))
        assert len(decoded) > 0


def test_make_token_contains_payload(unsub_instance):
    """Token payload should contain rid, cid, ts."""
    token = unsub_instance.make_token(recipient_id=789, campaign_id=101)
    
    payload = unsub_instance._verify_token(token)
    
    assert payload["rid"] == 789
    assert payload["cid"] == 101
    assert isinstance(payload["ts"], int)
    assert abs(payload["ts"] - int(time.time())) < 5


def test_list_unsubscribe_headers(unsub_instance):
    """Headers should include both https and mailto URLs plus One-Click."""
    token = unsub_instance.make_token(recipient_id=1, campaign_id=2)
    headers = unsub_instance.list_unsubscribe_headers(token)
    
    assert "List-Unsubscribe" in headers
    assert "List-Unsubscribe-Post" in headers
    
    unsub_header = headers["List-Unsubscribe"]
    assert f"https://example.com/u?t={token}" in unsub_header
    assert "mailto:" in unsub_header
    
    assert headers["List-Unsubscribe-Post"] == "List-Unsubscribe=One-Click"


def test_handle_one_click_success(unsub_instance, mock_store):
    """One-click handler should suppress email and return success."""
    rid = mock_store.add_recipient("test@example.com", "example.com")
    token = unsub_instance.make_token(recipient_id=rid, campaign_id=100)
    
    result = unsub_instance.handle_one_click(token)
    
    assert result.ok is True
    assert result.recipient_id == rid
    assert result.already is False
    
    # Verify suppression added
    assert mock_store.suppression_exists("email", "test@example.com")


def test_handle_one_click_idempotent(unsub_instance, mock_store):
    """Repeated one-click should return already=True, no error."""
    rid = mock_store.add_recipient("repeat@example.com", "example.com")
    token = unsub_instance.make_token(recipient_id=rid, campaign_id=200)
    
    result1 = unsub_instance.handle_one_click(token)
    assert result1.already is False
    
    result2 = unsub_instance.handle_one_click(token)
    assert result2.ok is True
    assert result2.already is True
    assert result2.recipient_id == rid


# ---- Boundary Cases ----

def test_make_token_zero_ids(unsub_instance):
    """Token with rid=0, cid=0 should be valid."""
    token = unsub_instance.make_token(recipient_id=0, campaign_id=0)
    payload = unsub_instance._verify_token(token)
    
    assert payload["rid"] == 0
    assert payload["cid"] == 0


def test_make_token_large_ids(unsub_instance):
    """Token with large IDs should work."""
    token = unsub_instance.make_token(recipient_id=999999999, campaign_id=888888888)
    payload = unsub_instance._verify_token(token)
    
    assert payload["rid"] == 999999999
    assert payload["cid"] == 888888888


def test_verify_token_tampered_signature(unsub_instance):
    """Tampered signature should raise ValidationError with specific message."""
    token = unsub_instance.make_token(recipient_id=1, campaign_id=2)
    
    payload_b64, sig_b64 = token.split(".", 1)

    # XOR first byte of decoded signature: guaranteed byte change, valid base64.
    # (Flipping the last b64 char is flaky: its low bits are discarded by decode.)
    sig_padded = sig_b64 + "=" * ((4 - len(sig_b64) % 4) % 4)
    sig_bytes = bytearray(base64.urlsafe_b64decode(sig_padded.encode("ascii")))
    sig_bytes[0] ^= 0x01
    tampered_sig = base64.urlsafe_b64encode(bytes(sig_bytes)).rstrip(b"=").decode("ascii")
    tampered_token = f"{payload_b64}.{tampered_sig}"
    
    with pytest.raises(ValidationError, match="Signature mismatch"):
        unsub_instance._verify_token(tampered_token)


def test_verify_token_invalid_base64(unsub_instance):
    """Invalid base64 in payload part should raise ValidationError.

    Needs a dot (else fails earlier as "Token format invalid") and a payload
    part that actually breaks the decoder: "A" pads to "A===" which binascii
    rejects (1 data char can't be 1 more than a multiple of 4).
    """
    with pytest.raises(ValidationError, match="Invalid base64"):
        unsub_instance._verify_token("A.AAAA")


def test_verify_token_missing_pipe(unsub_instance):
    """Token without dot separator should fail."""
    malformed = base64.urlsafe_b64encode(b"nopipe").decode("ascii").rstrip("=")
    
    with pytest.raises(ValidationError, match="Token format invalid"):
        unsub_instance._verify_token(malformed)


def test_verify_token_invalid_json(unsub_instance):
    """Token with invalid JSON payload should fail."""
    payload_b64 = base64.urlsafe_b64encode(b"notjson").decode("ascii").rstrip("=")
    sig_b64 = base64.urlsafe_b64encode(b"a" * 32).decode("ascii").rstrip("=")
    token = f"{payload_b64}.{sig_b64}"
    
    with pytest.raises(ValidationError, match="Invalid JSON payload"):
        unsub_instance._verify_token(token)


def test_verify_token_missing_fields(unsub_instance):
    """Token payload missing required fields should fail."""
    payload = {"rid": 1}  # missing cid, ts
    payload_json = json.dumps(payload, separators=(",", ":"))
    payload_b64 = base64.urlsafe_b64encode(payload_json.encode()).decode("ascii").rstrip("=")
    
    sig_bytes = hmac.new(unsub_instance._secret, payload_json.encode(), hashlib.sha256).digest()
    sig_b64 = base64.urlsafe_b64encode(sig_bytes).decode("ascii").rstrip("=")
    
    token = f"{payload_b64}.{sig_b64}"
    
    with pytest.raises(ValidationError, match="Missing or invalid field"):
        unsub_instance._verify_token(token)


def test_handle_one_click_nonexistent_recipient(unsub_instance):
    """Nonexistent recipient should return ok=False per contract."""
    token = unsub_instance.make_token(recipient_id=99999, campaign_id=1)
    
    result = unsub_instance.handle_one_click(token)
    assert result.ok is False
    assert result.recipient_id == 99999
    assert result.already is False


# ---- Security Invariants ----

def test_signature_changes_with_different_secret(mock_config, mock_store, mock_suppression):
    """Token from different secret should not verify."""
    from sender.unsub import Unsub
    
    unsub1 = Unsub(mock_config, mock_store, mock_suppression)
    token1 = unsub1.make_token(recipient_id=1, campaign_id=2)
    
    # Change secret
    os.environ["TEST_UNSUB_SECRET"] = "different-secret-key-32-bytes!"
    unsub2 = Unsub(mock_config, mock_store, mock_suppression)
    
    with pytest.raises(ValidationError, match="Signature mismatch"):
        unsub2._verify_token(token1)
    
    os.environ["TEST_UNSUB_SECRET"] = "test-secret-key-32-bytes-long!!"


def test_suppression_immediate(unsub_instance, mock_store):
    """Suppression should be added immediately, before returning."""
    rid = mock_store.add_recipient("immediate@example.com", "example.com")
    token = unsub_instance.make_token(recipient_id=rid, campaign_id=3)
    
    assert not mock_store.suppression_exists("email", "immediate@example.com")
    
    unsub_instance.handle_one_click(token)
    
    assert mock_store.suppression_exists("email", "immediate@example.com")


def test_token_replay_safe(unsub_instance, mock_store):
    """Same token can be replayed (idempotent), no side effects."""
    rid = mock_store.add_recipient("replay@example.com", "example.com")
    token = unsub_instance.make_token(recipient_id=rid, campaign_id=4)
    
    for _ in range(3):
        result = unsub_instance.handle_one_click(token)
        assert result.ok is True
    
    # Suppression should exist exactly once
    conn = mock_store.conn
    cur = conn.execute(
        "SELECT COUNT(*) FROM suppression WHERE scope='email' AND value='replay@example.com'"
    )
    count = cur.fetchone()[0]
    assert count == 1


def test_config_missing_secret_raises(temp_db, mock_suppression):
    """Missing UNSUB_SECRET env var should raise at init."""
    from sender.unsub import Unsub
    
    class LegalCfg:
        unsub_base_url = "https://example.com/u"
        unsub_secret_env = "MISSING_SECRET"
        entity = "ООО Руспром"
    
    class BadConfig:
        def legal(self):
            return LegalCfg()
    
    class MockStore:
        pass
    
    with pytest.raises(ValueError, match="Missing environment variable: MISSING_SECRET"):
        Unsub(BadConfig(), MockStore(), mock_suppression)


def test_headers_include_campaign_token(unsub_instance):
    """Headers for different campaigns should use different tokens."""
    token1 = unsub_instance.make_token(recipient_id=1, campaign_id=10)
    token2 = unsub_instance.make_token(recipient_id=1, campaign_id=20)
    
    headers1 = unsub_instance.list_unsubscribe_headers(token1)
    headers2 = unsub_instance.list_unsubscribe_headers(token2)
    
    assert token1 in headers1["List-Unsubscribe"]
    assert token2 in headers2["List-Unsubscribe"]
    assert headers1["List-Unsubscribe"] != headers2["List-Unsubscribe"]


def test_token_timestamp_freshness(unsub_instance):
    """Token timestamp should be within a few seconds of creation."""
    before = int(time.time())
    token = unsub_instance.make_token(recipient_id=5, campaign_id=6)
    after = int(time.time())
    
    payload = unsub_instance._verify_token(token)
    ts = payload["ts"]
    
    assert before <= ts <= after + 1


# ---- Edge Cases ----

def test_base64_padding_variants(unsub_instance):
    """Token verification should handle base64 padding correctly."""
    # Generate tokens with different payload lengths (different padding)
    for rid in [1, 12, 123, 1234, 12345]:
        token = unsub_instance.make_token(recipient_id=rid, campaign_id=1)
        payload = unsub_instance._verify_token(token)
        assert payload["rid"] == rid


def test_unicode_in_base_url(mock_config, mock_store, mock_suppression):
    """Base URL with unicode should work (though not recommended)."""
    from sender.unsub import Unsub
    
    class LegalCfg:
        unsub_base_url = "https://пример.рф/u"
        unsub_secret_env = "TEST_UNSUB_SECRET"
        entity = "ООО Руспром"
    
    class UnicodeConfig:
        def legal(self):
            return LegalCfg()
    
    os.environ["TEST_UNSUB_SECRET"] = "test-secret-key"
    unsub = Unsub(UnicodeConfig(), mock_store, mock_suppression)
    token = unsub.make_token(recipient_id=1, campaign_id=1)
    headers = unsub.list_unsubscribe_headers(token)
    
    assert "https://пример.рф/u?" in headers["List-Unsubscribe"]
    os.environ["TEST_UNSUB_SECRET"] = "test-secret-key-32-bytes-long!!"


def test_suppression_reason_recorded(unsub_instance, mock_store):
    """Suppression entry should record reason='unsubscribe'."""
    rid = mock_store.add_recipient("reason@example.com", "example.com")
    token = unsub_instance.make_token(recipient_id=rid, campaign_id=7)
    
    unsub_instance.handle_one_click(token)
    
    conn = mock_store.conn
    cur = conn.execute(
        "SELECT reason, source FROM suppression WHERE scope='email' AND value='reason@example.com'"
    )
    row = cur.fetchone()
    
    assert row is not None
    assert row[0] == "unsubscribe"
    assert row[1] == "one_click"


def test_handle_one_click_records_campaign_id(unsub_instance, mock_store):
    """Suppression entry should include campaign_id from token."""
    rid = mock_store.add_recipient("campaign@example.com", "example.com")
    token = unsub_instance.make_token(recipient_id=rid, campaign_id=999)
    
    unsub_instance.handle_one_click(token)
    
    conn = mock_store.conn
    cur = conn.execute(
        "SELECT campaign_id FROM suppression WHERE scope='email' AND value='campaign@example.com'"
    )
    row = cur.fetchone()
    
    assert row is not None
    assert row[0] == 999


def test_zagolovok_otpiski_mozhno_vyklyuchit():
    """legal.list_unsub_header: false — в письме ни ссылки, ни заголовка.

    Почтовик рисует по этому заголовку свою кнопку «Отписаться»: для письма,
    которое продажник пишет от своего имени, это метка «рассылка». Канал отказа
    остаётся в теле письма и в приёме входящих (ответ → стоп-лист).
    """
    from unittest.mock import Mock

    sender_obj = Mock()
    sender_obj.config = Mock()
    sender_obj.config.get = lambda key, default=None: (
        False if key == "legal.list_unsub_header" else default)
    mb = Mock()
    mb.mailbox_id = "a.balakirev@compressor-store.ru"

    from sender.sender import Sender
    assert Sender._list_unsubscribe_headers(sender_obj, "tok", mb) == {}
