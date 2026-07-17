# FILE: sender/tests/test_suppression.py
"""Юниты для sender/suppression.py.

Store — реальная временная sqlite (минимальная реализация контрактных методов
suppression_lookup / suppression_add). Сеть/остальной DAL не задействованы.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone

import pytest

from sender.suppression import (
    Recipient,
    Suppression,
    SuppressionEntry,
    SuppressionIn,
    ValidationError,
    normalize_domain,
    normalize_email,
    normalize_inn,
)


# --------------------------------------------------------------------------- #
# Реальный sqlite-store: только suppression-часть контракта §1/§2.
# --------------------------------------------------------------------------- #
class SqliteStore:
    def __init__(self, path: str):
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys=ON")
        self._init_schema()

    def _init_schema(self) -> None:
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS suppression (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                scope       TEXT NOT NULL,
                value       TEXT NOT NULL,
                reason      TEXT NOT NULL,
                source      TEXT,
                campaign_id INTEGER,
                created_at  TEXT NOT NULL,
                expires_at  TEXT
            );
            CREATE UNIQUE INDEX IF NOT EXISTS ux_suppression_scope_val
                ON suppression(scope, value);
            CREATE INDEX IF NOT EXISTS ix_suppression_reason
                ON suppression(reason);
            """
        )
        self.conn.commit()

    def suppression_add(self, e: SuppressionIn) -> tuple[int, bool]:
        now = datetime.now(timezone.utc).isoformat()
        exp = e.expires_at.isoformat() if e.expires_at else None
        cur = self.conn.execute(
            "INSERT INTO suppression"
            "(scope, value, reason, source, campaign_id, created_at, expires_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(scope, value) DO NOTHING",
            (e.scope, e.value, e.reason, e.source, e.campaign_id, now, exp),
        )
        self.conn.commit()
        if cur.rowcount == 1:
            return int(cur.lastrowid), True
        row = self.conn.execute(
            "SELECT id FROM suppression WHERE scope=? AND value=?",
            (e.scope, e.value),
        ).fetchone()
        return (int(row["id"]) if row else -1), False

    def suppression_lookup(self, *, email, domain, inn):
        now = datetime.now(timezone.utc).isoformat()
        for scope, value in (("email", email), ("domain", domain), ("inn", inn)):
            if not value:
                continue
            row = self.conn.execute(
                "SELECT * FROM suppression WHERE scope=? AND value=? "
                "AND (expires_at IS NULL OR expires_at > ?)",
                (scope, value, now),
            ).fetchone()
            if row:
                return self._to_entry(row)
        return None

    @staticmethod
    def _to_entry(row) -> SuppressionEntry:
        return SuppressionEntry(
            id=row["id"],
            scope=row["scope"],
            value=row["value"],
            reason=row["reason"],
            source=row["source"],
            campaign_id=row["campaign_id"],
            created_at=datetime.fromisoformat(row["created_at"]),
            expires_at=(
                datetime.fromisoformat(row["expires_at"])
                if row["expires_at"]
                else None
            ),
        )

    def close(self) -> None:
        self.conn.close()


# --------------------------------------------------------------------------- #
# Фикстуры и хелперы.
# --------------------------------------------------------------------------- #
@pytest.fixture()
def store(tmp_path):
    s = SqliteStore(str(tmp_path / "sender.db"))
    yield s
    s.close()


@pytest.fixture()
def supp(store):
    return Suppression(store)


def mk_recipient(email="user@example.com", domain=None, inn=None) -> Recipient:
    if domain is None:
        domain = email.split("@", 1)[1] if "@" in email else ""
    now = datetime.now(timezone.utc)
    return Recipient(
        id=1,
        email=email,
        domain=domain,
        inn=inn,
        company_name=None,
        okved=None,
        segment=None,
        bitrix_id=None,
        contact_name=None,
        mx_provider=None,
        valid_status="unknown",
        catch_all=None,
        role_based=None,
        disposable=None,
        source=None,
        extra={},
        created_at=now,
        updated_at=now,
    )


# --------------------------------------------------------------------------- #
# Нормализация.
# --------------------------------------------------------------------------- #
def test_normalize_email_basic():
    assert normalize_email("  John.Doe@Example.COM ") == "john.doe@example.com"


def test_normalize_email_mailto_and_brackets():
    assert normalize_email("Mailto:Foo@Bar.com") == "foo@bar.com"
    assert normalize_email('"Foo Bar" <Foo@Bar.com>') == "foo@bar.com"


def test_normalize_email_strips_www_in_domain():
    assert normalize_email("info@www.example.com") == "info@example.com"


@pytest.mark.parametrize("bad", ["", "no-at-sign", "a@@b.com", "@example.com", "x@"])
def test_normalize_email_invalid(bad):
    with pytest.raises(ValidationError):
        normalize_email(bad)


def test_normalize_domain_from_url_and_www():
    assert normalize_domain("http://www.Example.com/some/path?q=1") == "example.com"
    assert normalize_domain("WWW.Corp.RU.") == "corp.ru"


def test_normalize_domain_strips_port_and_userpart():
    assert normalize_domain("mail.example.com:993") == "mail.example.com"
    assert normalize_domain("user@example.com") == "example.com"


def test_normalize_domain_empty_raises():
    with pytest.raises(ValidationError):
        normalize_domain("   ")


def test_normalize_inn_valid():
    assert normalize_inn("7707 083 893") == "7707083893"
    assert normalize_inn("123456789012") == "123456789012"


@pytest.mark.parametrize("bad", ["", "abc", "12345", "1234567890123"])
def test_normalize_inn_invalid(bad):
    with pytest.raises(ValidationError):
        normalize_inn(bad)


# --------------------------------------------------------------------------- #
# Добавление и идемпотентность.
# --------------------------------------------------------------------------- #
def test_add_email_is_idempotent(supp):
    assert supp.add_email("A@B.com", "manual") is True
    # повтор с другим регистром → та же нормализованная запись, создания нет
    assert supp.add_email("a@b.com", "manual") is False


def test_add_domain_and_inn(supp):
    assert supp.add_domain("Competitor.RU", "competitor") is True
    assert supp.add_inn("7707083893", "manual") is True
    assert supp.add_domain("competitor.ru", "competitor") is False


def test_add_invalid_reason_raises(supp):
    with pytest.raises(ValidationError):
        supp.add_email("x@y.com", "not-a-reason")


def test_add_invalid_email_raises(supp):
    with pytest.raises(ValidationError):
        supp.add_email("broken-email", "manual")


# --------------------------------------------------------------------------- #
# Проверка: email → domain → inn.
# --------------------------------------------------------------------------- #
def test_is_suppressed_by_email(supp):
    supp.add_email("target@corp.com", "complaint")
    entry = supp.is_suppressed(mk_recipient("Target@Corp.com"))
    assert entry is not None
    assert entry.scope == "email"
    assert entry.reason == "complaint"


def test_is_suppressed_by_domain(supp):
    supp.add_domain("corp.com", "competitor")
    entry = supp.is_suppressed(mk_recipient("someone@corp.com"))
    assert entry is not None
    assert entry.scope == "domain"


def test_is_suppressed_by_inn(supp):
    supp.add_inn("7707083893", "manual")
    entry = supp.is_suppressed(mk_recipient("no-hit@nowhere.com", inn="7707083893"))
    assert entry is not None
    assert entry.scope == "inn"


def test_is_suppressed_priority_email_over_domain(supp):
    supp.add_domain("corp.com", "competitor")
    supp.add_email("target@corp.com", "unsubscribe")
    entry = supp.is_suppressed(mk_recipient("target@corp.com"))
    assert entry is not None
    assert entry.scope == "email"  # email имеет приоритет над domain


def test_is_suppressed_none(supp):
    assert supp.is_suppressed(mk_recipient("clean@fresh.com")) is None


def test_is_suppressed_derives_domain_from_email(supp):
    # у получателя нет заполненного domain → выводим из email
    supp.add_domain("corp.com", "competitor")
    rcpt = mk_recipient("lead@corp.com", domain="")
    entry = supp.is_suppressed(rcpt)
    assert entry is not None
    assert entry.scope == "domain"


# --------------------------------------------------------------------------- #
# Истечение (expires_at).
# --------------------------------------------------------------------------- #
def test_expired_entry_not_matched(store, supp):
    past = datetime.now(timezone.utc) - timedelta(hours=1)
    store.suppression_add(
        SuppressionIn(
            scope="email",
            value=normalize_email("old@corp.com"),
            reason="manual",
            expires_at=past,
        )
    )
    assert supp.is_suppressed(mk_recipient("old@corp.com")) is None


def test_future_expiry_still_matched(store, supp):
    future = datetime.now(timezone.utc) + timedelta(days=1)
    store.suppression_add(
        SuppressionIn(
            scope="email",
            value=normalize_email("temp@corp.com"),
            reason="manual",
            expires_at=future,
        )
    )
    entry = supp.is_suppressed(mk_recipient("temp@corp.com"))
    assert entry is not None
    assert entry.scope == "email"


# --------------------------------------------------------------------------- #
# Импорт списков.
# --------------------------------------------------------------------------- #
def test_import_competitors_dedup_and_count(supp):
    values = [
        "Competitor.com",
        "http://competitor.com/path",  # дубль после нормализации
        "# comment",
        "",
        "other.RU",
        "bad domain with space @@",  # невалидное → пропуск
    ]
    created = supp.import_competitors(values, scope="domain")
    assert created == 2  # competitor.com + other.ru
    assert supp.is_suppressed(mk_recipient("x@competitor.com")) is not None
    assert supp.is_suppressed(mk_recipient("y@other.ru")) is not None


def test_import_competitors_idempotent(supp):
    assert supp.import_competitors(["rival.com"]) == 1
    assert supp.import_competitors(["rival.com", "RIVAL.com"]) == 0


def test_import_file(tmp_path, supp):
    f = tmp_path / "suppression-domains.txt"
    f.write_text(
        "\n".join(
            [
                "# competitor domains",
                "alpha.com",
                "beta.com   # inline comment",
                "",
                "  ALPHA.com  ",  # дубль
                "http://gamma.com/",
            ]
        ),
        encoding="utf-8",
    )
    created = supp.import_file(f, scope="domain", reason="competitor")
    assert created == 3  # alpha, beta, gamma
    assert supp.is_suppressed(mk_recipient("a@beta.com")) is not None


def test_import_glob(tmp_path, supp):
    (tmp_path / "suppression-1.txt").write_text("one.com\n", encoding="utf-8")
    (tmp_path / "suppression-2.txt").write_text("two.com\nthree.com\n", encoding="utf-8")
    (tmp_path / "ignore.txt").write_text("skip.com\n", encoding="utf-8")

    created = supp.import_glob(
        str(tmp_path / "suppression-*.txt"), scope="domain", reason="competitor"
    )
    assert created == 3
    assert supp.is_suppressed(mk_recipient("x@three.com")) is not None
    assert supp.is_suppressed(mk_recipient("x@skip.com")) is None  # не подпадал под glob


def test_import_file_email_scope(tmp_path, supp):
    f = tmp_path / "suppression-emails.txt"
    f.write_text("Unsub@Client.com\nbad-email\n", encoding="utf-8")
    created = supp.import_file(f, scope="email", reason="unsubscribe")
    assert created == 1  # bad-email пропущен
    entry = supp.is_suppressed(mk_recipient("unsub@client.com"))
    assert entry is not None and entry.reason == "unsubscribe"
