# FILE: sender/store.py
"""SQLite DAL для сервиса холодной рассылки «Руспром».

Единственный писатель в БД. Все методы идемпотентны, где это осмысленно.
Модуль не зависит от других модулей сервиса — только stdlib.

Инварианты (см. §5 контракта), реализуемые здесь:
- дедуп на уровне БД (UNIQUE email / idempotency_key / dedup_key);
- suppression-first + «не слать ответившему» внутри той же транзакции, что и lease;
- kill-switch: claim не выдаёт сообщения для паузнутых ящиков;
- резюмируемость: recover_stale возвращает зависшие 'sending' в 'scheduled';
  дневные счётчики персистентны, сбрасываются только по смене day_key.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Iterator, Optional, Sequence

# --------------------------------------------------------------------------- #
# Исключения (общий хребет сервиса)
# --------------------------------------------------------------------------- #


class SenderError(Exception):
    ...


class ConfigError(SenderError):
    ...


class StoreError(SenderError):
    ...


class SuppressedError(SenderError):
    ...


class ValidationError(SenderError):
    ...


class PersonalizationGateError(SenderError):
    ...


class SendError(SenderError):
    ...


class RateLimitExceeded(SendError):
    ...


class GateTrippedError(SenderError):
    ...


class TransientError(SenderError):
    ...


# --------------------------------------------------------------------------- #
# DTO / сущности (§3). Определены здесь, т.к. store не импортит другие модули.
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class RecipientIn:
    email: str
    domain: str
    inn: Optional[str] = None
    company_name: Optional[str] = None
    okved: Optional[str] = None
    segment: Optional[str] = None
    bitrix_id: Optional[str] = None
    contact_name: Optional[str] = None
    source: Optional[str] = None
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CampaignIn:
    name: str
    legal_entity: str
    legal_inn: str
    provider_pool: Optional[str] = None
    config: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SequenceStepIn:
    campaign_id: int
    step_index: int
    delay_hours: int
    subject_tmpl: str
    body_tmpl: str
    engagement_gate: str = "all"
    include_legal: bool = False


@dataclass(frozen=True)
class MessageIn:
    idempotency_key: str
    campaign_id: int
    recipient_id: int
    sequence_step_id: int
    scheduled_at: datetime
    thread_id: Optional[str] = None
    in_reply_to: Optional[str] = None


@dataclass(frozen=True)
class EventIn:
    dedup_key: str
    event_type: str
    event_ts: datetime
    message_id: Optional[int] = None
    recipient_id: Optional[int] = None
    campaign_id: Optional[int] = None
    mailbox_id: Optional[str] = None
    provider: Optional[str] = None
    detail: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SuppressionIn:
    scope: str
    value: str
    reason: str
    source: str = ""
    campaign_id: Optional[int] = None
    expires_at: Optional[datetime] = None


@dataclass(frozen=True)
class Recipient:
    id: int
    email: str
    domain: str
    inn: Optional[str]
    company_name: Optional[str]
    okved: Optional[str]
    segment: Optional[str]
    bitrix_id: Optional[str]
    contact_name: Optional[str]
    mx_provider: Optional[str]
    valid_status: str
    catch_all: Optional[bool]
    role_based: Optional[bool]
    disposable: Optional[bool]
    source: Optional[str]
    extra: dict[str, Any]
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class Campaign:
    id: int
    name: str
    status: str
    legal_entity: str
    legal_inn: str
    provider_pool: Optional[str]
    config: dict[str, Any]
    created_at: datetime
    started_at: Optional[datetime]


@dataclass(frozen=True)
class SequenceStep:
    id: int
    campaign_id: int
    step_index: int
    delay_hours: int
    subject_tmpl: str
    body_tmpl: str
    engagement_gate: str
    include_legal: bool
    active: bool


@dataclass(frozen=True)
class Message:
    id: int
    idempotency_key: str
    campaign_id: int
    recipient_id: int
    sequence_step_id: int
    mailbox_id: Optional[str]
    status: str
    scheduled_at: Optional[datetime]
    claimed_at: Optional[datetime]
    sent_at: Optional[datetime]
    rfc_message_id: Optional[str]
    in_reply_to: Optional[str]
    thread_id: Optional[str]
    subject: Optional[str]
    body_rendered: Optional[str]
    unsub_token: Optional[str]
    attempt_count: int
    last_error: Optional[str]


@dataclass(frozen=True)
class SuppressionEntry:
    id: int
    scope: str
    value: str
    reason: str
    source: Optional[str]
    campaign_id: Optional[int]
    created_at: datetime
    expires_at: Optional[datetime]


@dataclass(frozen=True)
class Event:
    """Событие журнала на выход (list_events/get_thread). Вход — EventIn."""
    id: int
    dedup_key: str
    event_type: str
    message_id: Optional[int]
    recipient_id: Optional[int]
    campaign_id: Optional[int]
    mailbox_id: Optional[str]
    provider: Optional[str]
    event_ts: datetime
    detail: dict
    created_at: datetime


@dataclass
class MailboxState:
    mailbox_id: str
    provider: str
    day_key: str
    sent_today: int
    sent_total: int
    ramp_day: int
    daily_limit: int
    last_sent_at: Optional[datetime]
    paused: bool
    pause_reason: Optional[str]


@dataclass
class WarmupState:
    mailbox_id: str
    phase: str
    ramp_day: int
    warmup_target: int
    warmup_sent_today: int
    reputation_score: Optional[float]
    day_key: str
    last_warmup_at: Optional[datetime]


# --------------------------------------------------------------------------- #
# Хелперы времени / типов
# --------------------------------------------------------------------------- #

# Фиксированная длина → лексикографическая сортировка совпадает с временной.
_ISO_FMT = "%Y-%m-%dT%H:%M:%S.%f"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _to_iso(dt: Optional[datetime]) -> Optional[str]:
    """UTC ISO-8601 фиксированного формата. Наивный datetime трактуем как UTC."""
    if dt is None:
        return None
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt.strftime(_ISO_FMT)


def _now_iso() -> str:
    return _to_iso(_now())  # type: ignore[return-value]


def _from_iso(s: Optional[str]) -> Optional[datetime]:
    if s is None:
        return None
    return datetime.strptime(s, _ISO_FMT).replace(tzinfo=timezone.utc)


def _b(x: Any) -> Optional[bool]:
    return None if x is None else bool(x)


def _json_dump(d: Optional[dict[str, Any]]) -> Optional[str]:
    if d is None:
        return None
    return json.dumps(d, ensure_ascii=False, sort_keys=True)


def _json_load(s: Optional[str]) -> dict[str, Any]:
    if not s:
        return {}
    try:
        val = json.loads(s)
    except json.JSONDecodeError:
        return {}
    return val if isinstance(val, dict) else {}


# --------------------------------------------------------------------------- #
# Схема
# --------------------------------------------------------------------------- #

_SCHEMA = """
CREATE TABLE IF NOT EXISTS recipients (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    inn           TEXT,
    email         TEXT NOT NULL,
    domain        TEXT NOT NULL,
    company_name  TEXT,
    okved         TEXT,
    segment       TEXT,
    bitrix_id     TEXT,
    contact_name  TEXT,
    mx_provider   TEXT,
    valid_status  TEXT NOT NULL DEFAULT 'unknown',
    catch_all     INTEGER,
    role_based    INTEGER,
    disposable    INTEGER,
    source        TEXT,
    extra_json    TEXT,
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_recipients_email ON recipients(email);
CREATE INDEX IF NOT EXISTS ix_recipients_domain   ON recipients(domain);
CREATE INDEX IF NOT EXISTS ix_recipients_inn      ON recipients(inn);
CREATE INDEX IF NOT EXISTS ix_recipients_provider ON recipients(mx_provider);
CREATE INDEX IF NOT EXISTS ix_recipients_valid    ON recipients(valid_status);

CREATE TABLE IF NOT EXISTS campaigns (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    name           TEXT NOT NULL,
    status         TEXT NOT NULL DEFAULT 'draft',
    legal_entity   TEXT NOT NULL,
    legal_inn      TEXT NOT NULL,
    provider_pool  TEXT,
    config_json    TEXT,
    created_at     TEXT NOT NULL,
    started_at     TEXT,
    paused_at      TEXT,
    updated_at     TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_campaigns_status ON campaigns(status);

CREATE TABLE IF NOT EXISTS sequence_steps (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    campaign_id    INTEGER NOT NULL REFERENCES campaigns(id) ON DELETE CASCADE,
    step_index     INTEGER NOT NULL,
    delay_hours    INTEGER NOT NULL,
    subject_tmpl   TEXT NOT NULL,
    body_tmpl      TEXT NOT NULL,
    engagement_gate TEXT NOT NULL DEFAULT 'all',
    include_legal  INTEGER NOT NULL DEFAULT 0,
    active         INTEGER NOT NULL DEFAULT 1,
    created_at     TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_step_campaign_idx ON sequence_steps(campaign_id, step_index);

CREATE TABLE IF NOT EXISTS messages (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    idempotency_key  TEXT NOT NULL,
    campaign_id      INTEGER NOT NULL REFERENCES campaigns(id),
    recipient_id     INTEGER NOT NULL REFERENCES recipients(id),
    sequence_step_id INTEGER NOT NULL REFERENCES sequence_steps(id),
    mailbox_id       TEXT,
    status           TEXT NOT NULL DEFAULT 'pending',
    scheduled_at     TEXT,
    claimed_at       TEXT,
    sent_at          TEXT,
    rfc_message_id   TEXT,
    in_reply_to      TEXT,
    thread_id        TEXT,
    subject          TEXT,
    body_rendered    TEXT,
    unsub_token      TEXT,
    attempt_count    INTEGER NOT NULL DEFAULT 0,
    last_error       TEXT,
    created_at       TEXT NOT NULL,
    updated_at       TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_messages_idem  ON messages(idempotency_key);
CREATE UNIQUE INDEX IF NOT EXISTS ux_messages_rfcid ON messages(rfc_message_id) WHERE rfc_message_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS ix_messages_status_sched ON messages(status, scheduled_at);
CREATE INDEX IF NOT EXISTS ix_messages_mailbox      ON messages(mailbox_id, status);
CREATE INDEX IF NOT EXISTS ix_messages_recipient    ON messages(recipient_id);
CREATE INDEX IF NOT EXISTS ix_messages_thread       ON messages(thread_id);
CREATE INDEX IF NOT EXISTS ix_messages_campaign     ON messages(campaign_id, status);

CREATE TABLE IF NOT EXISTS events (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    dedup_key    TEXT NOT NULL,
    event_type   TEXT NOT NULL,
    message_id   INTEGER REFERENCES messages(id),
    recipient_id INTEGER REFERENCES recipients(id),
    campaign_id  INTEGER REFERENCES campaigns(id),
    mailbox_id   TEXT,
    provider     TEXT,
    event_ts     TEXT NOT NULL,
    detail_json  TEXT,
    created_at   TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_events_dedup ON events(dedup_key);
CREATE INDEX IF NOT EXISTS ix_events_type_ts   ON events(event_type, event_ts);
CREATE INDEX IF NOT EXISTS ix_events_recipient ON events(recipient_id, event_type);
CREATE INDEX IF NOT EXISTS ix_events_campaign  ON events(campaign_id, event_type);
CREATE INDEX IF NOT EXISTS ix_events_mailbox   ON events(mailbox_id, event_type, event_ts);

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
CREATE UNIQUE INDEX IF NOT EXISTS ux_suppression_scope_val ON suppression(scope, value);
CREATE INDEX IF NOT EXISTS ix_suppression_reason ON suppression(reason);

CREATE TABLE IF NOT EXISTS mailbox_state (
    mailbox_id   TEXT PRIMARY KEY,
    provider     TEXT NOT NULL,
    day_key      TEXT NOT NULL,
    sent_today   INTEGER NOT NULL DEFAULT 0,
    sent_total   INTEGER NOT NULL DEFAULT 0,
    ramp_day     INTEGER NOT NULL DEFAULT 0,
    daily_limit  INTEGER NOT NULL,
    last_sent_at TEXT,
    paused       INTEGER NOT NULL DEFAULT 0,
    pause_reason TEXT,
    updated_at   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_mailbox_paused ON mailbox_state(paused);

CREATE TABLE IF NOT EXISTS warmup_state (
    mailbox_id        TEXT PRIMARY KEY REFERENCES mailbox_state(mailbox_id),
    phase             TEXT NOT NULL DEFAULT 'ramp',
    ramp_day          INTEGER NOT NULL DEFAULT 0,
    warmup_target     INTEGER NOT NULL DEFAULT 0,
    warmup_sent_today INTEGER NOT NULL DEFAULT 0,
    reputation_score  REAL,
    day_key           TEXT NOT NULL,
    last_warmup_at    TEXT,
    updated_at        TEXT NOT NULL
);

-- ФЗ-152: журнал правовых оснований и отказов (защита при жалобе в РКН).
-- Append-only; basis фиксирует юр-линию (решение владельца 2026-07-18:
-- «адресное B2B-предложение»). Дубли безвредны, история важнее уникальности.
CREATE TABLE IF NOT EXISTS consent_log (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    recipient_id INTEGER REFERENCES recipients(id),
    email        TEXT NOT NULL,
    action       TEXT NOT NULL,      -- send|unsubscribe|complaint|consent|manual_optout
    basis        TEXT NOT NULL,      -- direct_b2b_offer|consent|legitimate_interest
    source       TEXT,               -- send:{message_id}|one_click|imap_complaint|operator
    campaign_id  INTEGER,
    detail_json  TEXT,
    created_at   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_consent_email ON consent_log(email, created_at);
CREATE INDEX IF NOT EXISTS ix_consent_action ON consent_log(action, created_at);
"""


# --------------------------------------------------------------------------- #
# Store
# --------------------------------------------------------------------------- #


class Store:
    """DAL поверх sqlite3. Потокобезопасен через единый RLock на соединение."""

    def __init__(self, db_path: str | Path):
        self._db_path = str(db_path)
        self._lock = threading.RLock()
        # isolation_level=None → ручное управление транзакциями (BEGIN IMMEDIATE).
        self._conn = sqlite3.connect(
            self._db_path, isolation_level=None, check_same_thread=False
        )
        self._conn.row_factory = sqlite3.Row
        self._apply_pragmas()

    # -- инфраструктура ----------------------------------------------------- #

    def _apply_pragmas(self) -> None:
        cur = self._conn
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA foreign_keys=ON")
        cur.execute("PRAGMA busy_timeout=5000")
        cur.execute("PRAGMA synchronous=NORMAL")

    def init_schema(self) -> None:
        """CREATE IF NOT EXISTS + PRAGMA. Идемпотентно."""
        with self._lock:
            self._apply_pragmas()
            self._conn.executescript(_SCHEMA)

    @contextmanager
    def transaction(self):
        """BEGIN IMMEDIATE ... COMMIT/ROLLBACK. Реентерабелен по потоку через RLock."""
        with self._lock:
            self._conn.execute("BEGIN IMMEDIATE")
            try:
                yield self._conn
                self._conn.execute("COMMIT")
            except Exception:
                self._conn.execute("ROLLBACK")
                raise

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    # -- резюм -------------------------------------------------------------- #

    def recover_stale(self, lease_ttl_sec: int) -> int:
        """Зависшие 'sending' со старым/пустым lease → обратно в 'scheduled'."""
        threshold = _to_iso(_now() - timedelta(seconds=lease_ttl_sec))
        now_iso = _now_iso()
        with self.transaction() as conn:
            cur = conn.execute(
                """
                UPDATE messages
                   SET status='scheduled', claimed_at=NULL, updated_at=?
                 WHERE status='sending'
                   AND (claimed_at IS NULL OR claimed_at <= ?)
                """,
                (now_iso, threshold),
            )
            return cur.rowcount

    # -- recipients --------------------------------------------------------- #

    def upsert_recipient(self, r: RecipientIn) -> int:
        """ON CONFLICT(email): не затираем существующие непустые поля NULL-ами."""
        now_iso = _now_iso()
        with self.transaction() as conn:
            conn.execute(
                """
                INSERT INTO recipients
                    (email, domain, inn, company_name, okved, segment, bitrix_id,
                     contact_name, source, extra_json, created_at, updated_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(email) DO UPDATE SET
                    domain=excluded.domain,
                    inn=COALESCE(excluded.inn, recipients.inn),
                    company_name=COALESCE(excluded.company_name, recipients.company_name),
                    okved=COALESCE(excluded.okved, recipients.okved),
                    segment=COALESCE(excluded.segment, recipients.segment),
                    bitrix_id=COALESCE(excluded.bitrix_id, recipients.bitrix_id),
                    contact_name=COALESCE(excluded.contact_name, recipients.contact_name),
                    source=COALESCE(excluded.source, recipients.source),
                    extra_json=excluded.extra_json,
                    updated_at=excluded.updated_at
                """,
                (
                    r.email, r.domain, r.inn, r.company_name, r.okved, r.segment,
                    r.bitrix_id, r.contact_name, r.source, _json_dump(r.extra),
                    now_iso, now_iso,
                ),
            )
            row = conn.execute(
                "SELECT id FROM recipients WHERE email=?", (r.email,)
            ).fetchone()
            return int(row["id"])

    def log_consent(
        self,
        *,
        email: str,
        action: str,
        recipient_id: Optional[int] = None,
        basis: str = "direct_b2b_offer",
        source: str = "",
        campaign_id: Optional[int] = None,
        detail: Optional[dict] = None,
    ) -> int:
        """ФЗ-152: запись в журнал оснований/отказов (append-only)."""
        with self.transaction() as conn:
            cur = conn.execute(
                """
                INSERT INTO consent_log
                    (recipient_id, email, action, basis, source, campaign_id,
                     detail_json, created_at)
                VALUES (?,?,?,?,?,?,?,?)
                """,
                (recipient_id, email.strip().lower(), action, basis, source,
                 campaign_id, _json_dump(detail or {}), _now_iso()),
            )
            return int(cur.lastrowid)

    def consent_history(self, email: str) -> list[dict]:
        """История по адресу для ответа РКН/жалобщику (от старых к новым)."""
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT recipient_id, email, action, basis, source, campaign_id,
                       detail_json, created_at
                  FROM consent_log
                 WHERE email = ?
                 ORDER BY created_at ASC, id ASC
                """,
                (email.strip().lower(),),
            ).fetchall()
        return [
            {
                "recipient_id": r["recipient_id"],
                "email": r["email"],
                "action": r["action"],
                "basis": r["basis"],
                "source": r["source"],
                "campaign_id": r["campaign_id"],
                "detail": _json_load(r["detail_json"]),
                "created_at": r["created_at"],
            }
            for r in rows
        ]

    def set_recipient_validation(
        self,
        recipient_id: int,
        *,
        valid_status: str,
        mx_provider: Optional[str] = None,
        catch_all: Optional[bool] = None,
        role_based: Optional[bool] = None,
        disposable: Optional[bool] = None,
    ) -> None:
        """Сток результата validation.validate() в строку получателя.

        До этого метода колонки mx_provider/valid_status существовали, но их
        никто не писал: valid_status оставался 'unknown', и
        cadence.plan_campaign(valid_status='valid') не запланировал бы никого.
        """
        with self.transaction() as conn:
            cur = conn.execute(
                """
                UPDATE recipients
                   SET valid_status = ?,
                       mx_provider  = COALESCE(?, mx_provider),
                       catch_all    = COALESCE(?, catch_all),
                       role_based   = COALESCE(?, role_based),
                       disposable   = COALESCE(?, disposable),
                       updated_at   = ?
                 WHERE id = ?
                """,
                (
                    valid_status, mx_provider,
                    None if catch_all is None else int(catch_all),
                    None if role_based is None else int(role_based),
                    None if disposable is None else int(disposable),
                    _now_iso(), recipient_id,
                ),
            )
            if cur.rowcount == 0:
                raise StoreError(f"recipient not found: {recipient_id}")

    def bulk_upsert_recipients(self, rows: Iterable[RecipientIn]) -> int:
        count = 0
        for r in rows:
            self.upsert_recipient(r)
            count += 1
        return count

    def get_recipient(self, recipient_id: int) -> Optional[Recipient]:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM recipients WHERE id=?", (recipient_id,)
            ).fetchone()
        return _row_to_recipient(row) if row else None

    def iter_recipients(
        self, *, valid_status: Optional[str] = None, provider: Optional[str] = None
    ) -> Iterator[Recipient]:
        sql = ["SELECT * FROM recipients WHERE 1=1"]
        params: list[Any] = []
        if valid_status is not None:
            sql.append("AND valid_status = ?")
            params.append(valid_status)
        if provider is not None:
            sql.append("AND mx_provider = ?")
            params.append(provider)
        sql.append("ORDER BY id")
        with self._lock:
            rows = self._conn.execute(" ".join(sql), params).fetchall()
        for row in rows:
            yield _row_to_recipient(row)

    # -- campaigns / steps -------------------------------------------------- #

    def create_campaign(self, c: CampaignIn) -> int:
        now_iso = _now_iso()
        with self.transaction() as conn:
            cur = conn.execute(
                """
                INSERT INTO campaigns
                    (name, status, legal_entity, legal_inn, provider_pool,
                     config_json, created_at, updated_at)
                VALUES (?, 'draft', ?, ?, ?, ?, ?, ?)
                """,
                (
                    c.name, c.legal_entity, c.legal_inn, c.provider_pool,
                    _json_dump(c.config), now_iso, now_iso,
                ),
            )
            return int(cur.lastrowid)

    def get_campaign(self, campaign_id: int) -> Optional[Campaign]:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM campaigns WHERE id=?", (campaign_id,)
            ).fetchone()
        return _row_to_campaign(row) if row else None

    def set_campaign_status(self, campaign_id: int, status: str) -> None:
        now_iso = _now_iso()
        with self.transaction() as conn:
            if status == "active":
                conn.execute(
                    """UPDATE campaigns
                          SET status=?, updated_at=?,
                              started_at=COALESCE(started_at, ?)
                        WHERE id=?""",
                    (status, now_iso, now_iso, campaign_id),
                )
            elif status == "paused":
                conn.execute(
                    "UPDATE campaigns SET status=?, paused_at=?, updated_at=? WHERE id=?",
                    (status, now_iso, now_iso, campaign_id),
                )
            else:
                conn.execute(
                    "UPDATE campaigns SET status=?, updated_at=? WHERE id=?",
                    (status, now_iso, campaign_id),
                )

    def add_step(self, s: SequenceStepIn) -> int:
        now_iso = _now_iso()
        with self.transaction() as conn:
            cur = conn.execute(
                """
                INSERT INTO sequence_steps
                    (campaign_id, step_index, delay_hours, subject_tmpl, body_tmpl,
                     engagement_gate, include_legal, active, created_at)
                VALUES (?,?,?,?,?,?,?,1,?)
                """,
                (
                    s.campaign_id, s.step_index, s.delay_hours, s.subject_tmpl,
                    s.body_tmpl, s.engagement_gate, 1 if s.include_legal else 0,
                    now_iso,
                ),
            )
            return int(cur.lastrowid)

    def get_steps(self, campaign_id: int) -> list[SequenceStep]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM sequence_steps WHERE campaign_id=? ORDER BY step_index",
                (campaign_id,),
            ).fetchall()
        return [_row_to_step(r) for r in rows]

    # -- messages (очередь) ------------------------------------------------- #

    def enqueue_message(self, m: MessageIn) -> tuple[int, bool]:
        """ON CONFLICT(idempotency_key) DO NOTHING → (message_id, created?)."""
        now_iso = _now_iso()
        with self.transaction() as conn:
            cur = conn.execute(
                """
                INSERT INTO messages
                    (idempotency_key, campaign_id, recipient_id, sequence_step_id,
                     status, scheduled_at, thread_id, in_reply_to,
                     created_at, updated_at)
                VALUES (?,?,?,?, 'scheduled', ?,?,?,?,?)
                ON CONFLICT(idempotency_key) DO NOTHING
                """,
                (
                    m.idempotency_key, m.campaign_id, m.recipient_id,
                    m.sequence_step_id, _to_iso(m.scheduled_at), m.thread_id,
                    m.in_reply_to, now_iso, now_iso,
                ),
            )
            if cur.rowcount == 1:
                return int(cur.lastrowid), True
            row = conn.execute(
                "SELECT id FROM messages WHERE idempotency_key=?",
                (m.idempotency_key,),
            ).fetchone()
            return int(row["id"]), False

    def claim_due_messages(
        self, *, now: datetime, mailbox_ids: Sequence[str], limit: int
    ) -> list[Message]:
        """Атомарно 'scheduled'→'sending'+claimed_at.

        Выдаёт только due-строки, у которых нет события reply по (recipient,campaign)
        и нет активной suppression (email→domain→inn). Строки, привязанные к ящику
        вне переданного (не-паузнутого) набора, не выдаются; неназначенные (NULL)
        допускаются. Всё внутри одной транзакции с lease.
        """
        if limit <= 0:
            return []
        now_iso = _to_iso(now)
        mb = list(mailbox_ids)
        if mb:
            placeholders = ",".join("?" for _ in mb)
            mailbox_clause = f"(m.mailbox_id IS NULL OR m.mailbox_id IN ({placeholders}))"
        else:
            mailbox_clause = "(m.mailbox_id IS NULL)"

        select_sql = f"""
            SELECT m.id AS mid
              FROM messages m
              JOIN recipients r ON r.id = m.recipient_id
             WHERE m.status = 'scheduled'
               AND m.scheduled_at IS NOT NULL
               AND m.scheduled_at <= ?
               AND {mailbox_clause}
               AND NOT EXISTS (
                   SELECT 1 FROM events e
                    WHERE e.event_type = 'reply'
                      AND e.recipient_id = m.recipient_id
                      AND e.campaign_id  = m.campaign_id
               )
               AND NOT EXISTS (
                   SELECT 1 FROM suppression s
                    WHERE (s.expires_at IS NULL OR s.expires_at > ?)
                      AND (
                            (s.scope='email'  AND s.value = r.email)
                         OR (s.scope='domain' AND s.value = r.domain)
                         OR (s.scope='inn'    AND r.inn IS NOT NULL AND s.value = r.inn)
                      )
               )
             ORDER BY m.scheduled_at ASC, m.id ASC
             LIMIT ?
        """
        params: list[Any] = [now_iso, *mb, now_iso, limit]

        with self.transaction() as conn:
            ids = [int(row["mid"]) for row in conn.execute(select_sql, params).fetchall()]
            if not ids:
                return []
            in_ids = ",".join("?" for _ in ids)
            conn.execute(
                f"""UPDATE messages
                       SET status='sending', claimed_at=?, updated_at=?
                     WHERE id IN ({in_ids})""",
                (now_iso, now_iso, *ids),
            )
            rows = conn.execute(
                f"SELECT * FROM messages WHERE id IN ({in_ids}) ORDER BY scheduled_at ASC, id ASC",
                ids,
            ).fetchall()
        return [_row_to_message(r) for r in rows]

    def mark_sent(self, message_id: int, rfc_message_id: str, sent_at: datetime) -> None:
        now_iso = _now_iso()
        with self.transaction() as conn:
            conn.execute(
                """UPDATE messages
                      SET status='sent', rfc_message_id=?, sent_at=?, updated_at=?
                    WHERE id=?""",
                (rfc_message_id, _to_iso(sent_at), now_iso, message_id),
            )

    def mark_failed(self, message_id: int, error: str, *, retryable: bool) -> None:
        """retryable → назад в 'scheduled' (снят lease); иначе финальный 'failed'."""
        now_iso = _now_iso()
        with self.transaction() as conn:
            if retryable:
                conn.execute(
                    """UPDATE messages
                          SET status='scheduled', claimed_at=NULL,
                              attempt_count=attempt_count+1, last_error=?, updated_at=?
                        WHERE id=?""",
                    (error, now_iso, message_id),
                )
            else:
                conn.execute(
                    """UPDATE messages
                          SET status='failed',
                              attempt_count=attempt_count+1, last_error=?, updated_at=?
                        WHERE id=?""",
                    (error, now_iso, message_id),
                )

    def mark_skipped(self, message_id: int, reason: str) -> None:
        now_iso = _now_iso()
        with self.transaction() as conn:
            conn.execute(
                "UPDATE messages SET status='skipped', last_error=?, updated_at=? WHERE id=?",
                (reason, now_iso, message_id),
            )

    def get_message(self, message_id: int) -> Optional[Message]:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM messages WHERE id=?", (message_id,)
            ).fetchone()
        return _row_to_message(row) if row else None

    def find_message_by_rfc_id(self, rfc_message_id: str) -> Optional[Message]:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM messages WHERE rfc_message_id=?", (rfc_message_id,)
            ).fetchone()
        return _row_to_message(row) if row else None

    # -- events (append-only) ---------------------------------------------- #

    def append_event(self, e: EventIn) -> tuple[int, bool]:
        """ON CONFLICT(dedup_key) DO NOTHING → (event_id, created?)."""
        now_iso = _now_iso()
        with self.transaction() as conn:
            cur = conn.execute(
                """
                INSERT INTO events
                    (dedup_key, event_type, message_id, recipient_id, campaign_id,
                     mailbox_id, provider, event_ts, detail_json, created_at)
                VALUES (?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(dedup_key) DO NOTHING
                """,
                (
                    e.dedup_key, e.event_type, e.message_id, e.recipient_id,
                    e.campaign_id, e.mailbox_id, e.provider, _to_iso(e.event_ts),
                    _json_dump(e.detail), now_iso,
                ),
            )
            if cur.rowcount == 1:
                return int(cur.lastrowid), True
            row = conn.execute(
                "SELECT id FROM events WHERE dedup_key=?", (e.dedup_key,)
            ).fetchone()
            return int(row["id"]), False

    def count_events(
        self,
        *,
        event_type: str,
        campaign_id: Optional[int] = None,
        domain: Optional[str] = None,
        mailbox_id: Optional[str] = None,
        sequence_step_id: Optional[int] = None,
        recipient_provider: Optional[str] = None,
        since: Optional[datetime] = None,
    ) -> int:
        # mailbox_id/sequence_step_id — фильтры, которых ждёт analytics.StoreReader:
        # mailbox_id — колонка events (индекс ix_events_mailbox), sequence_step_id —
        # через join events.message_id -> messages.sequence_step_id.
        # recipient_provider — репутационное измерение gates «× провайдер получателя»
        # (recipients.mx_provider; репутация Mail.ru и Яндекса считается раздельно).
        sql = ["SELECT COUNT(*) AS c FROM events e"]
        params: list[Any] = []
        if domain is not None or recipient_provider is not None:
            sql.append("JOIN recipients r ON r.id = e.recipient_id")
        if sequence_step_id is not None:
            sql.append("JOIN messages m ON m.id = e.message_id")
        sql.append("WHERE e.event_type = ?")
        params.append(event_type)
        if campaign_id is not None:
            sql.append("AND e.campaign_id = ?")
            params.append(campaign_id)
        if domain is not None:
            sql.append("AND r.domain = ?")
            params.append(domain)
        if recipient_provider is not None:
            sql.append("AND r.mx_provider = ?")
            params.append(recipient_provider)
        if mailbox_id is not None:
            sql.append("AND e.mailbox_id = ?")
            params.append(mailbox_id)
        if sequence_step_id is not None:
            sql.append("AND m.sequence_step_id = ?")
            params.append(sequence_step_id)
        if since is not None:
            sql.append("AND e.event_ts >= ?")
            params.append(_to_iso(since))
        with self._lock:
            row = self._conn.execute(" ".join(sql), params).fetchone()
        return int(row["c"])

    def last_event_ts(
        self, *, event_type: str, campaign_id: Optional[int] = None
    ) -> Optional[datetime]:
        """MAX(event_ts) события; нужен канареечной волне cadence («когда
        канарейка дослана» → окно ожидания DSN отсчитывается от неё)."""
        sql = ["SELECT MAX(event_ts) AS ts FROM events WHERE event_type = ?"]
        params: list[Any] = [event_type]
        if campaign_id is not None:
            sql.append("AND campaign_id = ?")
            params.append(campaign_id)
        with self._lock:
            row = self._conn.execute(" ".join(sql), params).fetchone()
        return _from_iso(row["ts"]) if row and row["ts"] else None

    def has_reply(self, recipient_id: int, campaign_id: int) -> bool:
        with self._lock:
            row = self._conn.execute(
                """SELECT 1 FROM events
                    WHERE event_type='reply' AND recipient_id=? AND campaign_id=?
                    LIMIT 1""",
                (recipient_id, campaign_id),
            ).fetchone()
        return row is not None

    # -- suppression -------------------------------------------------------- #

    def suppression_lookup(
        self, *, email: str, domain: str, inn: Optional[str]
    ) -> Optional[SuppressionEntry]:
        """Проверка в порядке email → domain → inn, только неистёкшие записи."""
        now_iso = _now_iso()
        with self._lock:
            for scope, value in (("email", email), ("domain", domain), ("inn", inn)):
                if value is None:
                    continue
                row = self._conn.execute(
                    """SELECT * FROM suppression
                        WHERE scope=? AND value=?
                          AND (expires_at IS NULL OR expires_at > ?)""",
                    (scope, value, now_iso),
                ).fetchone()
                if row:
                    return _row_to_suppression(row)
        return None

    def suppression_add(self, e: SuppressionIn) -> tuple[int, bool]:
        """ON CONFLICT(scope,value) DO NOTHING → (id, created?)."""
        now_iso = _now_iso()
        with self.transaction() as conn:
            cur = conn.execute(
                """
                INSERT INTO suppression
                    (scope, value, reason, source, campaign_id, created_at, expires_at)
                VALUES (?,?,?,?,?,?,?)
                ON CONFLICT(scope, value) DO NOTHING
                """,
                (
                    e.scope, e.value, e.reason, e.source, e.campaign_id,
                    now_iso, _to_iso(e.expires_at),
                ),
            )
            if cur.rowcount == 1:
                return int(cur.lastrowid), True
            row = conn.execute(
                "SELECT id FROM suppression WHERE scope=? AND value=?",
                (e.scope, e.value),
            ).fetchone()
            return int(row["id"]), False

    # -- mailbox / warmup state -------------------------------------------- #

    def get_mailbox_state(self, mailbox_id: str) -> Optional[MailboxState]:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM mailbox_state WHERE mailbox_id=?", (mailbox_id,)
            ).fetchone()
        return _row_to_mailbox_state(row) if row else None

    def iter_mailbox_states(self) -> list[MailboxState]:
        # список, не генератор: наружу нельзя отдавать курсор из-под self._lock
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM mailbox_state ORDER BY mailbox_id"
            ).fetchall()
        return [_row_to_mailbox_state(r) for r in rows]

    def upsert_mailbox_state(self, s: MailboxState) -> None:
        now_iso = _now_iso()
        with self.transaction() as conn:
            conn.execute(
                """
                INSERT INTO mailbox_state
                    (mailbox_id, provider, day_key, sent_today, sent_total, ramp_day,
                     daily_limit, last_sent_at, paused, pause_reason, updated_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(mailbox_id) DO UPDATE SET
                    provider=excluded.provider,
                    day_key=excluded.day_key,
                    sent_today=excluded.sent_today,
                    sent_total=excluded.sent_total,
                    ramp_day=excluded.ramp_day,
                    daily_limit=excluded.daily_limit,
                    last_sent_at=excluded.last_sent_at,
                    paused=excluded.paused,
                    pause_reason=excluded.pause_reason,
                    updated_at=excluded.updated_at
                """,
                (
                    s.mailbox_id, s.provider, s.day_key, s.sent_today, s.sent_total,
                    s.ramp_day, s.daily_limit, _to_iso(s.last_sent_at),
                    1 if s.paused else 0, s.pause_reason, now_iso,
                ),
            )

    def increment_sent(self, mailbox_id: str, *, now: datetime) -> MailboxState:
        """Атомарный инкремент. Смена day_key сбрасывает sent_today и +1 к ramp_day."""
        day_key = now.strftime("%Y-%m-%d")
        now_iso = _to_iso(now)
        updated = _now_iso()
        with self.transaction() as conn:
            row = conn.execute(
                "SELECT * FROM mailbox_state WHERE mailbox_id=?", (mailbox_id,)
            ).fetchone()
            if row is None:
                raise StoreError(f"mailbox_state not found: {mailbox_id}")
            if row["day_key"] != day_key:
                sent_today = 1
                ramp_day = int(row["ramp_day"]) + 1
            else:
                sent_today = int(row["sent_today"]) + 1
                ramp_day = int(row["ramp_day"])
            sent_total = int(row["sent_total"]) + 1
            conn.execute(
                """UPDATE mailbox_state
                      SET day_key=?, sent_today=?, sent_total=?, ramp_day=?,
                          last_sent_at=?, updated_at=?
                    WHERE mailbox_id=?""",
                (day_key, sent_today, sent_total, ramp_day, now_iso, updated, mailbox_id),
            )
        state = self.get_mailbox_state(mailbox_id)
        assert state is not None  # только что обновили
        return state

    def set_mailbox_paused(
        self, mailbox_id: str, paused: bool, reason: Optional[str]
    ) -> None:
        now_iso = _now_iso()
        with self.transaction() as conn:
            conn.execute(
                "UPDATE mailbox_state SET paused=?, pause_reason=?, updated_at=? WHERE mailbox_id=?",
                (1 if paused else 0, reason, now_iso, mailbox_id),
            )

    def get_warmup_state(self, mailbox_id: str) -> Optional[WarmupState]:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM warmup_state WHERE mailbox_id=?", (mailbox_id,)
            ).fetchone()
        return _row_to_warmup_state(row) if row else None

    def upsert_warmup_state(self, s: WarmupState) -> None:
        now_iso = _now_iso()
        with self.transaction() as conn:
            conn.execute(
                """
                INSERT INTO warmup_state
                    (mailbox_id, phase, ramp_day, warmup_target, warmup_sent_today,
                     reputation_score, day_key, last_warmup_at, updated_at)
                VALUES (?,?,?,?,?,?,?,?,?)
                ON CONFLICT(mailbox_id) DO UPDATE SET
                    phase=excluded.phase,
                    ramp_day=excluded.ramp_day,
                    warmup_target=excluded.warmup_target,
                    warmup_sent_today=excluded.warmup_sent_today,
                    reputation_score=excluded.reputation_score,
                    day_key=excluded.day_key,
                    last_warmup_at=excluded.last_warmup_at,
                    updated_at=excluded.updated_at
                """,
                (
                    s.mailbox_id, s.phase, s.ramp_day, s.warmup_target,
                    s.warmup_sent_today, s.reputation_score, s.day_key,
                    _to_iso(s.last_warmup_at), now_iso,
                ),
            )

    # -- NEW-BACKEND: чтение/сегментация для веб-панели (Фаза 2.1) ---------- #

    def query_recipients(
        self,
        filters: dict,
        *,
        limit: int = 100,
        offset: int = 0,
        order_by: str = "id",
    ) -> list["Recipient"]:
        """Сегмент-фильтрация базы для превью/поиска. Фильтры комбинируются AND."""
        join, jparams, where, wparams = self._recipient_query(filters)
        allowed = {"id", "email", "domain", "created_at", "updated_at"}
        col = order_by if order_by in allowed else "id"
        sql = f"SELECT r.* FROM recipients r{join}"
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += f" ORDER BY r.{col} ASC LIMIT ? OFFSET ?"
        params = [*jparams, *wparams, int(limit), int(offset)]
        with self._lock:
            rows = self._conn.execute(sql, params).fetchall()
        return [_row_to_recipient(row) for row in rows]

    def count_recipients(self, filters: dict) -> dict:
        """Счётчики сегмента (для live-превью): total + разбивки."""
        join, jparams, where, wparams = self._recipient_query(filters)
        params = [*jparams, *wparams]
        wsql = (" WHERE " + " AND ".join(where)) if where else ""
        with self._lock:
            total = int(self._conn.execute(
                f"SELECT COUNT(*) c FROM recipients r{join}{wsql}", params
            ).fetchone()["c"])
            by_status = {
                row["valid_status"]: int(row["c"]) for row in self._conn.execute(
                    f"SELECT r.valid_status, COUNT(*) c FROM recipients r{join}{wsql}"
                    " GROUP BY r.valid_status", params
                ).fetchall()
            }
            by_provider = {
                (row["mx_provider"] or "unknown"): int(row["c"]) for row in self._conn.execute(
                    f"SELECT r.mx_provider, COUNT(*) c FROM recipients r{join}{wsql}"
                    " GROUP BY r.mx_provider", params
                ).fetchall()
            }
        return {"total": total, "by_status": by_status, "by_provider": by_provider}

    def _recipient_query(self, filters: dict):
        """(join_sql, join_params, where_list, where_params) — всё позиционное.
        JOIN идёт до WHERE, поэтому его параметры собираются первыми."""
        join = ""
        jparams: list[Any] = []
        if filters.get("suppressed") is not None:
            join = (
                " LEFT JOIN suppression s ON "
                "(s.expires_at IS NULL OR s.expires_at > ?) AND ("
                "(s.scope='email' AND s.value=r.email) OR "
                "(s.scope='domain' AND s.value=r.domain) OR "
                "(s.scope='inn' AND r.inn IS NOT NULL AND s.value=r.inn))"
            )
            jparams.append(_now_iso())
        where: list[str] = []
        params: list[Any] = []

        def _in(col: str, val: Any) -> None:
            vals = val if isinstance(val, (list, tuple, set)) else [val]
            vals = [v for v in vals if v is not None]
            if not vals:
                return
            ph = ",".join("?" for _ in vals)
            where.append(f"{col} IN ({ph})")
            params.extend(vals)

        if filters.get("valid_status") is not None:
            _in("r.valid_status", filters["valid_status"])
        if filters.get("provider") is not None:
            _in("r.mx_provider", filters["provider"])
        if filters.get("domain") is not None:
            where.append("r.domain = ?")
            params.append(filters["domain"])
        if filters.get("domain_like"):
            where.append("r.domain LIKE ?")
            params.append(f"%{filters['domain_like']}%")
        if filters.get("inn") is not None:
            where.append("r.inn = ?")
            params.append(str(filters["inn"]))
        if filters.get("segment") is not None:
            where.append("r.segment = ?")
            params.append(filters["segment"])
        if filters.get("okved_prefix"):
            where.append("r.okved LIKE ?")
            params.append(f"{filters['okved_prefix']}%")
        if filters.get("company_like"):
            where.append("r.company_name LIKE ?")
            params.append(f"%{filters['company_like']}%")
        if filters.get("email_like"):
            where.append("r.email LIKE ?")
            params.append(f"%{filters['email_like']}%")
        if filters.get("created_after") is not None:
            where.append("r.created_at >= ?")
            params.append(_to_iso(filters["created_after"]))
        if filters.get("created_before") is not None:
            where.append("r.created_at <= ?")
            params.append(_to_iso(filters["created_before"]))
        # suppressed: LEFT JOIN (см. _recipient_join) — s.id NULL = не в suppression
        sup = filters.get("suppressed")
        if sup is not None:
            where.append("s.id IS NOT NULL" if sup else "s.id IS NULL")
        return join, jparams, where, params

    def list_events(
        self,
        *,
        event_type=None,
        campaign_id: Optional[int] = None,
        provider: Optional[str] = None,
        mailbox_id: Optional[str] = None,
        recipient_id: Optional[int] = None,
        since: Optional[datetime] = None,
        limit: int = 200,
        offset: int = 0,
    ) -> list["Event"]:
        sql = ["SELECT * FROM events WHERE 1=1"]
        params: list[Any] = []
        if event_type is not None:
            vals = event_type if isinstance(event_type, (list, tuple, set)) else [event_type]
            sql.append("AND event_type IN (%s)" % ",".join("?" for _ in vals))
            params.extend(vals)
        for col, val in (("campaign_id", campaign_id), ("provider", provider),
                         ("mailbox_id", mailbox_id), ("recipient_id", recipient_id)):
            if val is not None:
                sql.append(f"AND {col} = ?")
                params.append(val)
        if since is not None:
            sql.append("AND event_ts >= ?")
            params.append(_to_iso(since))
        sql.append("ORDER BY event_ts DESC, id DESC LIMIT ? OFFSET ?")
        params.extend([int(limit), int(offset)])
        with self._lock:
            rows = self._conn.execute(" ".join(sql), params).fetchall()
        return [_row_to_event(row) for row in rows]

    def list_campaigns(self, *, status=None) -> list["Campaign"]:
        sql = ["SELECT * FROM campaigns"]
        params: list[Any] = []
        if status is not None:
            vals = status if isinstance(status, (list, tuple, set)) else [status]
            sql.append("WHERE status IN (%s)" % ",".join("?" for _ in vals))
            params.extend(vals)
        sql.append("ORDER BY id DESC")
        with self._lock:
            rows = self._conn.execute(" ".join(sql), params).fetchall()
        return [_row_to_campaign(row) for row in rows]

    def list_messages(
        self,
        *,
        campaign_id: Optional[int] = None,
        recipient_id: Optional[int] = None,
        status=None,
        mailbox_id: Optional[str] = None,
        limit: int = 200,
        offset: int = 0,
    ) -> list["Message"]:
        sql = ["SELECT * FROM messages WHERE 1=1"]
        params: list[Any] = []
        for col, val in (("campaign_id", campaign_id), ("recipient_id", recipient_id),
                         ("mailbox_id", mailbox_id)):
            if val is not None:
                sql.append(f"AND {col} = ?")
                params.append(val)
        if status is not None:
            vals = status if isinstance(status, (list, tuple, set)) else [status]
            sql.append("AND status IN (%s)" % ",".join("?" for _ in vals))
            params.extend(vals)
        sql.append("ORDER BY COALESCE(scheduled_at,'') DESC, id DESC LIMIT ? OFFSET ?")
        params.extend([int(limit), int(offset)])
        with self._lock:
            rows = self._conn.execute(" ".join(sql), params).fetchall()
        return [_row_to_message(row) for row in rows]

    def get_thread(self, recipient_id: int, campaign_id: int) -> list["Event"]:
        """История переписки пары (получатель, кампания) в хронологии."""
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM events WHERE recipient_id=? AND campaign_id=? "
                "ORDER BY event_ts ASC, id ASC",
                (recipient_id, campaign_id),
            ).fetchall()
        return [_row_to_event(row) for row in rows]

    def iter_suppression(
        self, *, scope=None, reason=None, limit: int = 500, offset: int = 0
    ) -> list["SuppressionEntry"]:
        sql = ["SELECT * FROM suppression WHERE 1=1"]
        params: list[Any] = []
        if scope is not None:
            sql.append("AND scope = ?")
            params.append(scope)
        if reason is not None:
            sql.append("AND reason = ?")
            params.append(reason)
        sql.append("ORDER BY created_at DESC, id DESC LIMIT ? OFFSET ?")
        params.extend([int(limit), int(offset)])
        with self._lock:
            rows = self._conn.execute(" ".join(sql), params).fetchall()
        return [_row_to_suppression(row) for row in rows]

    def count_suppression(self, *, scope=None) -> dict:
        base = "FROM suppression"
        params: list[Any] = []
        if scope is not None:
            base += " WHERE scope = ?"
            params.append(scope)
        now_iso = _now_iso()
        with self._lock:
            total = int(self._conn.execute(f"SELECT COUNT(*) c {base}", params).fetchone()["c"])
            by_scope = {r["scope"]: int(r["c"]) for r in self._conn.execute(
                f"SELECT scope, COUNT(*) c {base} GROUP BY scope", params).fetchall()}
            by_reason = {r["reason"]: int(r["c"]) for r in self._conn.execute(
                f"SELECT reason, COUNT(*) c {base} GROUP BY reason", params).fetchall()}
            active = int(self._conn.execute(
                f"SELECT COUNT(*) c {base}{' AND' if scope else ' WHERE'} "
                "(expires_at IS NULL OR expires_at > ?)", [*params, now_iso]).fetchone()["c"])
        return {"total": total, "by_scope": by_scope, "by_reason": by_reason,
                "active": active, "expired": total - active}

    def suppression_remove(
        self, suppression_id: int, *, reason: str, actor: str = "operator"
    ) -> bool:
        """Аудируемое снятие suppression: в одной транзакции пишет consent_log
        (INSERT напрямую, не через log_consent — та открыла бы вложенную
        транзакцию), затем удаляет запись."""
        with self.transaction() as conn:
            row = conn.execute(
                "SELECT scope, value FROM suppression WHERE id=?", (suppression_id,)
            ).fetchone()
            if row is None:
                return False
            scope, value = row["scope"], row["value"]
            conn.execute(
                """
                INSERT INTO consent_log
                    (recipient_id, email, action, basis, source, campaign_id,
                     detail_json, created_at)
                VALUES (?,?,?,?,?,?,?,?)
                """,
                (None, value.strip().lower(), "suppression_removed",
                 "operator_decision", f"remove:{actor}", None,
                 _json_dump({"reason": reason, "scope": scope, "value": value}),
                 _now_iso()),
            )
            conn.execute("DELETE FROM suppression WHERE id=?", (suppression_id,))
        return True


# --------------------------------------------------------------------------- #
# row → dataclass
# --------------------------------------------------------------------------- #


def _row_to_event(row: sqlite3.Row) -> Event:
    return Event(
        id=int(row["id"]),
        dedup_key=row["dedup_key"],
        event_type=row["event_type"],
        message_id=row["message_id"],
        recipient_id=row["recipient_id"],
        campaign_id=row["campaign_id"],
        mailbox_id=row["mailbox_id"],
        provider=row["provider"],
        event_ts=_from_iso(row["event_ts"]),  # type: ignore[arg-type]
        detail=_json_load(row["detail_json"]),
        created_at=_from_iso(row["created_at"]),  # type: ignore[arg-type]
    )


def _row_to_recipient(row: sqlite3.Row) -> Recipient:
    return Recipient(
        id=int(row["id"]),
        email=row["email"],
        domain=row["domain"],
        inn=row["inn"],
        company_name=row["company_name"],
        okved=row["okved"],
        segment=row["segment"],
        bitrix_id=row["bitrix_id"],
        contact_name=row["contact_name"],
        mx_provider=row["mx_provider"],
        valid_status=row["valid_status"],
        catch_all=_b(row["catch_all"]),
        role_based=_b(row["role_based"]),
        disposable=_b(row["disposable"]),
        source=row["source"],
        extra=_json_load(row["extra_json"]),
        created_at=_from_iso(row["created_at"]),  # type: ignore[arg-type]
        updated_at=_from_iso(row["updated_at"]),  # type: ignore[arg-type]
    )


def _row_to_campaign(row: sqlite3.Row) -> Campaign:
    return Campaign(
        id=int(row["id"]),
        name=row["name"],
        status=row["status"],
        legal_entity=row["legal_entity"],
        legal_inn=row["legal_inn"],
        provider_pool=row["provider_pool"],
        config=_json_load(row["config_json"]),
        created_at=_from_iso(row["created_at"]),  # type: ignore[arg-type]
        started_at=_from_iso(row["started_at"]),
    )


def _row_to_step(row: sqlite3.Row) -> SequenceStep:
    return SequenceStep(
        id=int(row["id"]),
        campaign_id=int(row["campaign_id"]),
        step_index=int(row["step_index"]),
        delay_hours=int(row["delay_hours"]),
        subject_tmpl=row["subject_tmpl"],
        body_tmpl=row["body_tmpl"],
        engagement_gate=row["engagement_gate"],
        include_legal=bool(row["include_legal"]),
        active=bool(row["active"]),
    )


def _row_to_message(row: sqlite3.Row) -> Message:
    return Message(
        id=int(row["id"]),
        idempotency_key=row["idempotency_key"],
        campaign_id=int(row["campaign_id"]),
        recipient_id=int(row["recipient_id"]),
        sequence_step_id=int(row["sequence_step_id"]),
        mailbox_id=row["mailbox_id"],
        status=row["status"],
        scheduled_at=_from_iso(row["scheduled_at"]),
        claimed_at=_from_iso(row["claimed_at"]),
        sent_at=_from_iso(row["sent_at"]),
        rfc_message_id=row["rfc_message_id"],
        in_reply_to=row["in_reply_to"],
        thread_id=row["thread_id"],
        subject=row["subject"],
        body_rendered=row["body_rendered"],
        unsub_token=row["unsub_token"],
        attempt_count=int(row["attempt_count"]),
        last_error=row["last_error"],
    )


def _row_to_suppression(row: sqlite3.Row) -> SuppressionEntry:
    return SuppressionEntry(
        id=int(row["id"]),
        scope=row["scope"],
        value=row["value"],
        reason=row["reason"],
        source=row["source"],
        campaign_id=row["campaign_id"],
        created_at=_from_iso(row["created_at"]),  # type: ignore[arg-type]
        expires_at=_from_iso(row["expires_at"]),
    )


def _row_to_mailbox_state(row: sqlite3.Row) -> MailboxState:
    return MailboxState(
        mailbox_id=row["mailbox_id"],
        provider=row["provider"],
        day_key=row["day_key"],
        sent_today=int(row["sent_today"]),
        sent_total=int(row["sent_total"]),
        ramp_day=int(row["ramp_day"]),
        daily_limit=int(row["daily_limit"]),
        last_sent_at=_from_iso(row["last_sent_at"]),
        paused=bool(row["paused"]),
        pause_reason=row["pause_reason"],
    )


def _row_to_warmup_state(row: sqlite3.Row) -> WarmupState:
    return WarmupState(
        mailbox_id=row["mailbox_id"],
        phase=row["phase"],
        ramp_day=int(row["ramp_day"]),
        warmup_target=int(row["warmup_target"]),
        warmup_sent_today=int(row["warmup_sent_today"]),
        reputation_score=row["reputation_score"],
        day_key=row["day_key"],
        last_warmup_at=_from_iso(row["last_warmup_at"]),
    )
