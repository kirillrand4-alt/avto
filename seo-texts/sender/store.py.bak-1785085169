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


# Канонические источники (P1): исключения — errors.py, обменные DTO — dtos.py.
# Реэкспорт сохраняет исторические импорты `from sender.store import ...`.
from sender.errors import (  # noqa: F401
    SenderError, ConfigError, StoreError, SuppressedError, ValidationError, PersonalizationGateError, SendError, RateLimitExceeded, GateTrippedError, TransientError,
)
from sender.dtos import (  # noqa: F401
    RecipientIn, CampaignIn, SequenceStepIn, MessageIn, EventIn, SuppressionIn, Recipient, Campaign, SequenceStep, Message, SuppressionEntry, MailboxState, WarmupState,
)

# --------------------------------------------------------------------------- #
# Исключения (общий хребет сервиса)
# --------------------------------------------------------------------------- #


# --------------------------------------------------------------------------- #
# DTO / сущности (§3). Определены здесь, т.к. store не импортит другие модули.
# --------------------------------------------------------------------------- #


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


@dataclass(frozen=True)
class Lead:
    """Тёплый лид в очереди продажников (lead-desk, Фаза 2.1)."""
    id: int
    recipient_id: Optional[int]
    campaign_id: Optional[int]
    thread_id: Optional[str]
    email: str
    company_name: Optional[str]
    inn: Optional[str]
    status: str
    reply_kind: Optional[str]
    phone: Optional[str]
    need: Optional[str]
    readiness: Optional[int]
    assigned_to: Optional[int]
    source_event_id: Optional[int]
    bitrix_lead_id: Optional[int]
    dedup_key: str
    sla_due_at: Optional[datetime]
    version: int
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class User:
    id: int
    username: str
    email: Optional[str]
    password_hash: str
    role: str
    totp_secret: Optional[str]
    is_active: bool
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class Session:
    id: int
    user_id: int
    token_hash: str
    created_at: datetime
    expires_at: datetime
    revoked: bool
    user_agent: Optional[str]
    ip: Optional[str]


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


def _normalize_recipient_identity(
    email: str, domain: str, inn: Optional[str]
) -> tuple[str, str, Optional[str]]:
    """П1.1: канон идентичности получателя = канон suppression-значений.

    Импорт функций нормализации ленивый и с фолбэком: у suppression к store
    только TYPE_CHECKING-зависимость, цикла нет, но store обязан работать и в
    урезанных окружениях — тогда деградируем до strip/lower.
    """
    email = (email or "").strip().lower()
    raw_domain = (domain or "").strip() or (
        email.split("@", 1)[1] if "@" in email else ""
    )
    try:
        from sender.suppression import normalize_domain
        domain = normalize_domain(raw_domain) if raw_domain else raw_domain
    except Exception:  # noqa: BLE001 - канон отверг мусор → как есть
        domain = raw_domain.lower()
    if inn is not None:
        digits = "".join(ch for ch in str(inn) if ch.isdigit())
        inn = digits if len(digits) in (10, 12) else str(inn).strip()
    return email, domain, inn


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
    priority_max  INTEGER,
    priority_total REAL,
    pxr           REAL,
    region        TEXT,
    tz            TEXT,
    extra_json    TEXT,
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_recipients_email ON recipients(email);
CREATE INDEX IF NOT EXISTS ix_recipients_pxr ON recipients(pxr);
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

CREATE TABLE IF NOT EXISTS panel_settings (
    key        TEXT PRIMARY KEY,
    value      TEXT,
    updated_at TEXT
);
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

-- ── Веб-панель (Фаза 2.1): auth, lead-desk, audit ──────────────────────
-- Порядок важен для FK: users/sessions → leads/lead_events → audit_log.

CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    username      TEXT NOT NULL,
    email         TEXT,
    password_hash TEXT NOT NULL,     -- pbkdf2$<iters>$<salt_hex>$<hash_hex> (stdlib)
    role          TEXT NOT NULL DEFAULT 'manager',  -- owner|manager
    totp_secret   TEXT,              -- base32; NULL = 2FA выключена
    is_active     INTEGER NOT NULL DEFAULT 1,
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_users_username ON users(username);

CREATE TABLE IF NOT EXISTS sessions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL REFERENCES users(id),
    token_hash  TEXT NOT NULL,       -- sha256 выданного opaque-токена (сам токен не храним)
    created_at  TEXT NOT NULL,
    expires_at  TEXT NOT NULL,
    revoked     INTEGER NOT NULL DEFAULT 0,
    user_agent  TEXT,
    ip          TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_sessions_token ON sessions(token_hash);
CREATE INDEX IF NOT EXISTS ix_sessions_user ON sessions(user_id, revoked);

-- Ревью (подтверждено): защита панели от перебора пароля/TOTP. Счётчик
-- по username (не только существующим юзерам), durable.
CREATE TABLE IF NOT EXISTS auth_throttle (
    username     TEXT PRIMARY KEY,
    failed       INTEGER NOT NULL DEFAULT 0,
    locked_until TEXT,
    updated_at   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS leads (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    recipient_id   INTEGER REFERENCES recipients(id),
    campaign_id    INTEGER REFERENCES campaigns(id),
    thread_id      TEXT,
    email          TEXT NOT NULL,
    company_name   TEXT,
    inn            TEXT,
    status         TEXT NOT NULL DEFAULT 'new',  -- new|assigned|taken|qualified|unqualified|closed
    reply_kind     TEXT,              -- hot|interested|... из reply_classify
    phone          TEXT,
    need           TEXT,
    readiness      INTEGER,
    assigned_to    INTEGER REFERENCES users(id),
    source_event_id INTEGER REFERENCES events(id),
    bitrix_lead_id INTEGER,
    dedup_key      TEXT NOT NULL,     -- идемпотентность: thread|email
    sla_due_at     TEXT,
    version        INTEGER NOT NULL DEFAULT 0,  -- оптимистичная блокировка (CAS)
    created_at     TEXT NOT NULL,
    updated_at     TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_leads_dedup ON leads(dedup_key);
CREATE INDEX IF NOT EXISTS ix_leads_status   ON leads(status, created_at);
CREATE INDEX IF NOT EXISTS ix_leads_assigned ON leads(assigned_to, status);
CREATE INDEX IF NOT EXISTS ix_leads_sla      ON leads(sla_due_at);

CREATE TABLE IF NOT EXISTS lead_events (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    lead_id       INTEGER NOT NULL REFERENCES leads(id),
    actor_user_id INTEGER REFERENCES users(id),
    action        TEXT NOT NULL,     -- created|assigned|taken|status_changed|note|synced
    from_status   TEXT,
    to_status     TEXT,
    detail_json   TEXT,
    created_at    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_lead_events_lead ON lead_events(lead_id, created_at);

CREATE TABLE IF NOT EXISTS audit_log (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    actor_user_id INTEGER REFERENCES users(id),
    action       TEXT NOT NULL,      -- login|campaign_activate|pause|suppression_add|...
    entity_type  TEXT,
    entity_id    TEXT,
    detail_json  TEXT,
    ip           TEXT,
    created_at   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_audit_actor  ON audit_log(actor_user_id, created_at);
CREATE INDEX IF NOT EXISTS ix_audit_action ON audit_log(action, created_at);

-- Режим «подтвердить отправку» (ENGINEER-TASKS-CONFIRM-SEND, Задача 1):
-- каждое письмо калибровки ждёт решения оператора. Durable, идемпотентно
-- по (ИНН, email, campaign) через dedup_key. edited хранит правку И диф —
-- это золотые пары для дообучения промптов.
CREATE TABLE IF NOT EXISTS confirm_reviews (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    dedup_key      TEXT NOT NULL,    -- "<inn>|<email>|<campaign_id>" или "reply|..."
    campaign_id    INTEGER,
    recipient_id   INTEGER,
    message_id     INTEGER REFERENCES messages(id),
    inn            TEXT,
    email          TEXT NOT NULL,
    subject        TEXT NOT NULL,
    body           TEXT NOT NULL,
    panel_json     TEXT,             -- JSON инфо-панели оператора (Задача 2)
    status         TEXT NOT NULL DEFAULT 'pending',
                                     -- pending|approved|edited|skipped|stoplist|sent
    reason         TEXT,
    edited_subject TEXT,
    edited_body    TEXT,
    diff_text      TEXT,             -- unified diff оригинал -> правка
    decided_by     TEXT,
    decided_at     TEXT,
    kind           TEXT NOT NULL DEFAULT 'outbound',  -- outbound|reply
    in_reply_to    TEXT,             -- Message-ID входящего (для ответа)
    thread_id      TEXT,
    created_at     TEXT NOT NULL,
    updated_at     TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_confirm_dedup ON confirm_reviews(dedup_key);
CREATE INDEX IF NOT EXISTS ix_confirm_status ON confirm_reviews(status, id);

-- Лог отправок (Задача 3): рассыльщик владеет логом -> он и ведёт историю
-- контактов и 90-дневный заслон повторного касания.
CREATE TABLE IF NOT EXISTS send_log (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    inn            TEXT,
    email          TEXT NOT NULL,
    campaign_id    INTEGER,
    ts             TEXT NOT NULL,
    message_id     INTEGER,
    rfc_message_id TEXT,
    subject        TEXT,
    outcome        TEXT NOT NULL DEFAULT 'sent',  -- sent|bounced|replied|failed
    created_at     TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_sendlog_email ON send_log(email, ts);
CREATE INDEX IF NOT EXISTS ix_sendlog_inn   ON send_log(inn, ts);
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
        """CREATE IF NOT EXISTS + PRAGMA + миграции колонок. Идемпотентно."""
        with self._lock:
            self._apply_pragmas()
            # Миграция для БД, созданных ДО P1.6 (боевая на C:\sender):
            # CREATE IF NOT EXISTS новых колонок не добавляет — добираем
            # ALTER-ами ДО executescript, иначе индекс по pxr в _SCHEMA упадёт
            # на старой таблице. На свежей БД «no such table» глотается —
            # executescript создаст таблицу уже с колонками.
            for ddl in (
                "ALTER TABLE recipients ADD COLUMN priority_max INTEGER",
                "ALTER TABLE recipients ADD COLUMN priority_total REAL",
                "ALTER TABLE recipients ADD COLUMN pxr REAL",
                "ALTER TABLE recipients ADD COLUMN region TEXT",
                "ALTER TABLE recipients ADD COLUMN tz TEXT",
                # confirm_reviews: ручные ответы автоответчика (kind='reply')
                "ALTER TABLE confirm_reviews ADD COLUMN kind TEXT NOT NULL DEFAULT 'outbound'",
                "ALTER TABLE confirm_reviews ADD COLUMN in_reply_to TEXT",
                "ALTER TABLE confirm_reviews ADD COLUMN thread_id TEXT",
            ):
                try:
                    self._conn.execute(ddl)
                except sqlite3.OperationalError:
                    pass  # колонка уже есть или таблицы ещё нет
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

    def recover_stale_reviews(self, lease_ttl_sec: int = 900) -> int:
        """Ревью №12: карточка, которую панель успела перевести в 'sending_live'
        и упала (рестарт службы посреди approve), оставалась в этом статусе
        НАВСЕГДА — из очереди исчезла, оператор её больше не видит и повторить
        не может. Возвращаем такие карточки в 'pending' по истечении аренды.
        Возврат: сколько карточек освобождено."""
        threshold = _to_iso(_now() - timedelta(seconds=lease_ttl_sec))
        now_iso = _now_iso()
        with self.transaction() as conn:
            cur = conn.execute(
                "UPDATE confirm_reviews SET status='pending', updated_at=? "
                "WHERE status='sending_live' AND updated_at <= ?",
                (now_iso, threshold))
            return int(cur.rowcount or 0)

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
        """ON CONFLICT(email): не затираем существующие непустые поля NULL-ами.

        П1.1 (ФЗ-38): email/домен/ИНН нормализуются ЗДЕСЬ — тем же каноном, что
        значения suppression (suppression.normalize_*). Иначе SQL-сравнения
        стоп-листа (claim_due_messages, _recipient_query) промахиваются на
        регистре/пробелах, и отписанный адрес получает письмо.
        """
        email, domain, inn = _normalize_recipient_identity(r.email, r.domain, r.inn)
        now_iso = _now_iso()
        with self.transaction() as conn:
            conn.execute(
                """
                INSERT INTO recipients
                    (email, domain, inn, company_name, okved, segment, bitrix_id,
                     contact_name, source, priority_max, priority_total, pxr,
                     region, tz, extra_json, created_at, updated_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(email) DO UPDATE SET
                    domain=excluded.domain,
                    inn=COALESCE(excluded.inn, recipients.inn),
                    company_name=COALESCE(excluded.company_name, recipients.company_name),
                    okved=COALESCE(excluded.okved, recipients.okved),
                    segment=COALESCE(excluded.segment, recipients.segment),
                    bitrix_id=COALESCE(excluded.bitrix_id, recipients.bitrix_id),
                    contact_name=COALESCE(excluded.contact_name, recipients.contact_name),
                    source=COALESCE(excluded.source, recipients.source),
                    priority_max=COALESCE(excluded.priority_max, recipients.priority_max),
                    priority_total=COALESCE(excluded.priority_total, recipients.priority_total),
                    pxr=COALESCE(excluded.pxr, recipients.pxr),
                    region=COALESCE(excluded.region, recipients.region),
                    tz=COALESCE(excluded.tz, recipients.tz),
                    -- П3.4: пустой extra ({} или NULL — дефолт RecipientIn при
                    -- повторном импорте CSV) не перетирает накопленные
                    -- метаданные; непустой — заменяет, как раньше.
                    extra_json=COALESCE(
                        NULLIF(excluded.extra_json, '{}'), recipients.extra_json),
                    updated_at=excluded.updated_at
                """,
                (
                    email, domain, inn, r.company_name, r.okved, r.segment,
                    r.bitrix_id, r.contact_name, r.source,
                    r.priority_max, r.priority_total, r.pxr,
                    r.region, r.tz, _json_dump(r.extra),
                    now_iso, now_iso,
                ),
            )
            row = conn.execute(
                "SELECT id FROM recipients WHERE email=?", (email,)
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
        self, *, valid_status: Optional[str] = None, provider: Optional[str] = None,
        segment: Optional[str] = None, order: str = "id",
        min_priority_max: Optional[int] = None
    ) -> Iterator[Recipient]:
        """segment — таргетинг кампании; order — id|pxr_asc|pxr_desc (P1.6);
        min_priority_max — порог «Макс. балл по связке» (NULL проходит)."""
        sql = ["SELECT * FROM recipients WHERE 1=1"]
        params: list[Any] = []
        if valid_status is not None:
            sql.append("AND valid_status = ?")
            params.append(valid_status)
        if provider is not None:
            sql.append("AND mx_provider = ?")
            params.append(provider)
        if segment is not None:
            sql.append("AND segment = ?")
            params.append(segment)
        if min_priority_max is not None:
            # Порог отсекает ЗАВЕДОМО низкие баллы; получатели без балла (NULL)
            # проходят: отсутствие оценки не равно плохой оценке.
            sql.append("AND (priority_max IS NULL OR priority_max >= ?)")
            params.append(int(min_priority_max))
        if order == "pxr_asc":       # обкатка: дешёвые/малые первыми
            sql.append("ORDER BY COALESCE(pxr, 0) ASC, id")
        elif order == "pxr_desc":    # боевая фаза: приоритетные первыми
            sql.append("ORDER BY COALESCE(pxr, 0) DESC, id")
        else:
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

    def enqueue_message(self, m: MessageIn, *, status: str = "scheduled") -> tuple[int, bool]:
        """ON CONFLICT(idempotency_key) DO NOTHING → (message_id, created?).

        status: 'scheduled' (обычный поток) либо 'pending_review' — письмо
        калибровки confirm-send: claim_due его НЕ берёт (фильтр по
        status='scheduled'), в отправку переводит только решение оператора.
        """
        if status not in ("scheduled", "pending_review"):
            raise ValidationError(f"enqueue: недопустимый статус {status!r}")
        now_iso = _now_iso()
        with self.transaction() as conn:
            cur = conn.execute(
                """
                INSERT INTO messages
                    (idempotency_key, campaign_id, recipient_id, sequence_step_id,
                     status, scheduled_at, thread_id, in_reply_to,
                     created_at, updated_at)
                VALUES (?,?,?,?, ?, ?,?,?,?,?)
                ON CONFLICT(idempotency_key) DO NOTHING
                """,
                (
                    m.idempotency_key, m.campaign_id, m.recipient_id,
                    m.sequence_step_id, status, _to_iso(m.scheduled_at), m.thread_id,
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
                   -- П1.1: правая часть сравнений нормализуется на лету —
                   -- страховка для строк, записанных ДО нормализации в upsert.
                   -- П1.2: reason='unsubscribe' активен всегда (ФЗ-38, отписка
                   -- навсегда), даже если у строки выставлен expires_at.
                   SELECT 1 FROM suppression s
                    WHERE (s.expires_at IS NULL OR s.expires_at > ?
                           OR s.reason = 'unsubscribe')
                      AND (
                            (s.scope='email'  AND s.value = lower(trim(r.email)))
                         OR (s.scope='domain' AND s.value = lower(trim(r.domain)))
                         OR (s.scope='inn'    AND r.inn IS NOT NULL
                             AND s.value = replace(replace(trim(r.inn), ' ', ''), '-', ''))
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

    def mark_sent(self, message_id: int, rfc_message_id: str, sent_at: datetime,
                  *, mailbox_id: Optional[str] = None) -> None:
        """Письмо ушло. mailbox_id пишем, если он известен: при РУЧНОЙ отправке
        письмо не проходит claim, который обычно проставляет ящик, и в messages
        оставался NULL — потом было не понять, с какого ящика ушло письмо (а от
        этого зависит и ветка ответа, и ротация)."""
        now_iso = _now_iso()
        with self.transaction() as conn:
            if mailbox_id:
                conn.execute(
                    """UPDATE messages
                          SET status='sent', rfc_message_id=?, sent_at=?,
                              mailbox_id=COALESCE(mailbox_id, ?), updated_at=?
                        WHERE id=?""",
                    (rfc_message_id, _to_iso(sent_at), mailbox_id, now_iso,
                     message_id),
                )
            else:
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
                # Ревью №2: фильтра по статусу не было — письмо в 'pending_review'
                # (ручная очередь) при временной ошибке SMTP уезжало в
                # 'scheduled', то есть в АВТОМАТИЧЕСКУЮ отправку. Дальше «скип»
                # оператора не применялся (его UPDATE ждёт pending_review), и
                # после снятия холда письмо ушло бы компании, которую отклонили.
                # Ручную очередь не трогаем: там статус меняет только оператор.
                conn.execute(
                    """UPDATE messages
                          SET status='scheduled', claimed_at=NULL,
                              attempt_count=attempt_count+1, last_error=?, updated_at=?
                        WHERE id=? AND status IN ('sending','scheduled')""",
                    (error, now_iso, message_id),
                )
                # письмо ручной очереди: фиксируем ошибку, статус сохраняем
                conn.execute(
                    """UPDATE messages
                          SET attempt_count=attempt_count+1, last_error=?, updated_at=?
                        WHERE id=? AND status='pending_review'""",
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

    def mark_pending_review(self, message_id: int) -> None:
        """Confirm-режим оркестратора: письмо ушло в очередь подтверждений —
        выводим из авто-отправки (claim_due берёт только 'scheduled'/'sending').
        Решение оператора (approve/edit) вернёт его в 'scheduled'."""
        now_iso = _now_iso()
        with self.transaction() as conn:
            conn.execute(
                "UPDATE messages SET status='pending_review', claimed_at=NULL, "
                "updated_at=? WHERE id=?",
                (now_iso, message_id),
            )

    def mark_needs_data(self, message_id: int, reason: str) -> None:
        """§3 BASE-MERGE: пустые {news_object}/{city} и т.п. — письмо НЕ
        уходит пустышкой, лид падает в очередь «дозаполнить данные» с причиной.
        claim_due такие письма не берёт (фильтр status='scheduled')."""
        now_iso = _now_iso()
        with self.transaction() as conn:
            conn.execute(
                "UPDATE messages SET status='needs_data', last_error=?, "
                "updated_at=? WHERE id=?",
                (reason, now_iso, message_id),
            )

    def list_needs_data(self, *, limit: int = 100) -> list[dict]:
        """Очередь «дозаполнить данные»: письмо + получатель + причина."""
        with self._lock:
            rows = self._conn.execute(
                """SELECT m.id, m.campaign_id, m.recipient_id, m.last_error,
                          m.updated_at, r.email, r.inn, r.company_name
                     FROM messages m JOIN recipients r ON r.id=m.recipient_id
                    WHERE m.status='needs_data'
                    ORDER BY m.updated_at DESC LIMIT ?""",
                (int(limit),),
            ).fetchall()
        return [dict(r) for r in rows]

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
        recipient_id: Optional[int] = None,
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
        if recipient_id is not None:
            # П2.5: гейты каденции считают bounce ПО ПОЛУЧАТЕЛЮ (домен слишком
            # широк: один отказ на mail.ru резал бы весь общий домен).
            sql.append("AND e.recipient_id = ?")
            params.append(int(recipient_id))
        if since is not None:
            sql.append("AND e.event_ts >= ?")
            params.append(_to_iso(since))
        with self._lock:
            row = self._conn.execute(" ".join(sql), params).fetchone()
        return int(row["c"])

    def count_events_grouped(
        self, *, by: str, event_types: Sequence[str],
        since: Optional[datetime] = None,
    ) -> dict[str, dict[str, int]]:
        """Счётчики событий одним GROUP BY (ревью: gates делал N×3 запросов
        по доменам — 500 доменов = 1500 SQL на каждый evaluate_all).

        by: 'domain' | 'mailbox_id' | 'recipient_provider'.
        Возврат: {target: {event_type: n}}.
        """
        cols = {
            "domain": ("r.domain", True),
            "mailbox_id": ("e.mailbox_id", False),
            "recipient_provider": ("r.mx_provider", True),
        }
        if by not in cols:
            raise ValidationError(f"count_events_grouped: неизвестный разрез {by!r}")
        col, needs_join = cols[by]
        marks = ",".join("?" for _ in event_types)
        sql = [f"SELECT {col} AS g, e.event_type AS t, COUNT(*) AS c FROM events e"]
        if needs_join:
            sql.append("JOIN recipients r ON r.id = e.recipient_id")
        sql.append(f"WHERE e.event_type IN ({marks})")
        params: list[Any] = list(event_types)
        if since is not None:
            sql.append("AND e.event_ts >= ?")
            params.append(_to_iso(since))
        sql.append("GROUP BY 1, 2")
        out: dict[str, dict[str, int]] = {}
        with self._lock:
            for row in self._conn.execute(" ".join(sql), params).fetchall():
                g = row["g"]
                if g is None:
                    continue
                out.setdefault(str(g), {})[row["t"]] = int(row["c"])
        return out

    def last_sent_ts_for_region(self, region: str):
        """Время последнего sent-события по региону получателя (пер-регион пейсинг)."""
        with self._lock:
            row = self._conn.execute(
                """SELECT MAX(e.event_ts) AS ts FROM events e
                     JOIN recipients r ON r.id = e.recipient_id
                    WHERE e.event_type='sent' AND r.region = ?""",
                (region,)).fetchone()
        return _from_iso(row["ts"]) if row and row["ts"] else None

    def open_counts(self, recipient_ids: list[int]) -> dict[int, int]:
        """Число событий open по получателям одним GROUP BY (для ленты лидов).

        open — справочный сигнал (в РФ прокси картинок накручивают/гасят
        открытия, OPEN-TRACKING-SPEC.md); в гейтах не участвует.
        """
        ids = [int(r) for r in recipient_ids]
        if not ids:
            return {}
        marks = ",".join("?" for _ in ids)
        with self._lock:
            rows = self._conn.execute(
                f"""SELECT recipient_id AS rid, COUNT(*) AS c FROM events
                     WHERE event_type='open' AND recipient_id IN ({marks})
                     GROUP BY recipient_id""",
                ids).fetchall()
        return {int(r["rid"]): int(r["c"]) for r in rows}

    def dialog_thread(self, recipient_id: int, *, limit: int = 200) -> list[dict]:
        """Лента диалога по контакту: исходящие + входящие одной хронологией.

        Исходящие — отправленные письма (messages.sent_at IS NOT NULL);
        входящие — reply/reply_auto/complaint/dsn события (текст в
        detail_json.snippet). Каждый элемент: {direction: out|in, ts, kind,
        subject, body, mailbox_id, status}. Сортировка по времени по возрастанию
        (старые сверху — как в почтовом клиенте)."""
        rid = int(recipient_id)
        items: list[dict] = []
        with self._lock:
            outs = self._conn.execute(
                """SELECT id, sent_at, subject, body_rendered, mailbox_id,
                          status, thread_id
                     FROM messages
                    WHERE recipient_id=? AND sent_at IS NOT NULL
                    ORDER BY sent_at ASC LIMIT ?""",
                (rid, int(limit))).fetchall()
            ins = self._conn.execute(
                """SELECT id, event_type, event_ts, mailbox_id, detail_json
                     FROM events
                    WHERE recipient_id=?
                      AND event_type IN ('reply','reply_auto','complaint','dsn','bounce')
                    ORDER BY event_ts ASC LIMIT ?""",
                (rid, int(limit))).fetchall()
        for r in outs:
            items.append({
                "direction": "out", "ts": r["sent_at"], "kind": "sent",
                "subject": r["subject"] or "",
                "body": r["body_rendered"] or "",
                "mailbox_id": r["mailbox_id"] or "",
                "status": r["status"], "message_id": r["id"],
                "thread_id": r["thread_id"] or ""})
        for r in ins:
            detail = _json_load(r["detail_json"])
            items.append({
                "direction": "in", "ts": r["event_ts"],
                "kind": r["event_type"],
                "subject": (detail.get("headers") or {}).get("Subject", ""),
                "body": detail.get("snippet") or "",
                "mailbox_id": r["mailbox_id"] or "",
                "reply_kind": detail.get("reply_kind") or "",
                "event_id": r["id"]})
        items.sort(key=lambda x: str(x.get("ts") or ""))
        return items

    def dialog_thread_company(self, inn: str, *, limit: int = 200) -> list[dict]:
        """Вся переписка с КОМПАНИЕЙ (#64): по всем адресам всех получателей
        этого ИНН, плюс ручные отправки и ответы из send_log, которых нет в
        messages (у ответа нет строки messages). Хронология единая; каждый
        элемент несёт email, чтобы оператор видел, с каким контактом шёл
        разговор."""
        digits = "".join(c for c in str(inn or "") if c.isdigit())
        if not digits:
            return []
        with self._lock:
            rids = [(r["id"], r["email"]) for r in self._conn.execute(
                "SELECT id, email FROM recipients WHERE inn=?", (digits,))]
        items: list[dict] = []
        seen_rfc: set = set()
        for rid, email in rids:
            for it in self.dialog_thread(rid, limit=limit):
                it["email"] = email
                items.append(it)
        # ручные отправки/ответы: в send_log есть, в messages может не быть
        with self._lock:
            logs = self._conn.execute(
                """SELECT email, ts, subject, outcome, rfc_message_id
                     FROM send_log WHERE inn=? ORDER BY ts ASC LIMIT ?""",
                (digits, int(limit))).fetchall()
            rfc_known = {r["rfc_message_id"] for r in self._conn.execute(
                """SELECT m.rfc_message_id FROM messages m
                     JOIN recipients rc ON rc.id = m.recipient_id
                    WHERE rc.inn=? AND m.rfc_message_id IS NOT NULL""",
                (digits,))}
        for r in logs:
            rfc = r["rfc_message_id"]
            if rfc and (rfc in rfc_known or rfc in seen_rfc):
                continue
            if rfc:
                seen_rfc.add(rfc)
            items.append({
                "direction": "out", "ts": r["ts"],
                "kind": r["outcome"] or "sent",
                "subject": r["subject"] or "", "body": "",
                "mailbox_id": "", "email": r["email"] or ""})
        items.sort(key=lambda x: str(x.get("ts") or ""))
        return items[:limit]

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
        """Проверка в порядке email → domain → inn, только неистёкшие записи.

        П1.2: reason='unsubscribe' не истекает никогда — отписка по ФЗ-38
        соблюдается навсегда, даже если старой строке выставили expires_at.
        """
        now_iso = _now_iso()
        with self._lock:
            for scope, value in (("email", email), ("domain", domain), ("inn", inn)):
                if value is None:
                    continue
                row = self._conn.execute(
                    """SELECT * FROM suppression
                        WHERE scope=? AND value=?
                          AND (expires_at IS NULL OR expires_at > ?
                               OR reason = 'unsubscribe')""",
                    (scope, value, now_iso),
                ).fetchone()
                if row:
                    return _row_to_suppression(row)
        return None

    def suppression_add(self, e: SuppressionIn) -> tuple[int, bool]:
        """Идемпотентное добавление → (id, created?).

        П1.2 (ФЗ-38, отписка навсегда):
          * unsubscribe пишется БЕССРОЧНО — переданный expires_at игнорируется;
          * unsubscribe АПГРЕЙДИТ существующую запись другого reason (раньше
            DO NOTHING молча оставлял competitor-TTL, тот истекал — и адрес
            снова получал письма вопреки отписке); апгрейд считается created=True,
            чтобы вызывающий код записал отказ в consent_log;
          * запись с reason='unsubscribe' никогда не понижается другим reason.
        """
        now_iso = _now_iso()
        expires = None if e.reason == "unsubscribe" else _to_iso(e.expires_at)
        with self.transaction() as conn:
            cur = conn.execute(
                """
                INSERT INTO suppression
                    (scope, value, reason, source, campaign_id, created_at, expires_at)
                VALUES (?,?,?,?,?,?,?)
                ON CONFLICT(scope, value) DO UPDATE SET
                    reason = excluded.reason,
                    source = excluded.source,
                    campaign_id = COALESCE(excluded.campaign_id, suppression.campaign_id),
                    expires_at = NULL
                WHERE excluded.reason = 'unsubscribe'
                  AND suppression.reason <> 'unsubscribe'
                """,
                (
                    e.scope, e.value, e.reason, e.source, e.campaign_id,
                    now_iso, expires,
                ),
            )
            if cur.rowcount == 1:
                row = conn.execute(
                    "SELECT id FROM suppression WHERE scope=? AND value=?",
                    (e.scope, e.value),
                ).fetchone()
                return int(row["id"]), True
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

    def increment_sent(
        self, mailbox_id: str, *, now: datetime, day_key: Optional[str] = None
    ) -> MailboxState:
        """Атомарный инкремент. Смена day_key сбрасывает sent_today и +1 к ramp_day.

        П2.7: границу дня определяет вызывающий (sender передаёт дату в зоне
        конфига — той же, в которой живёт окно отправки). Без day_key —
        прежняя UTC-дата (совместимость юнитов и старых вызовов).
        """
        if day_key is None:
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
            # П1.1: lower(trim()) на стороне получателя — страховка для строк,
            # записанных до нормализации; П1.2: unsubscribe активен всегда.
            join = (
                " LEFT JOIN suppression s ON "
                "(s.expires_at IS NULL OR s.expires_at > ? OR s.reason='unsubscribe')"
                " AND ("
                "(s.scope='email' AND s.value=lower(trim(r.email))) OR "
                "(s.scope='domain' AND s.value=lower(trim(r.domain))) OR "
                "(s.scope='inn' AND r.inn IS NOT NULL"
                " AND s.value=replace(replace(trim(r.inn),' ',''),'-','')))"
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
        транзакцию), затем удаляет запись.

        П1.2: запись reason='unsubscribe' снять НЕЛЬЗЯ (ФЗ-38 — отписка
        соблюдается навсегда; оператор не вправе вернуть адрес в рассылку).
        """
        with self.transaction() as conn:
            row = conn.execute(
                "SELECT scope, value, reason FROM suppression WHERE id=?",
                (suppression_id,),
            ).fetchone()
            if row is None:
                return False
            if row["reason"] == "unsubscribe":
                raise ValidationError(
                    "запись об отписке не снимается: отписка по ФЗ-38 бессрочна"
                )
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

    # -- confirm-send: очередь подтверждений (Задача 1) --------------------- #

    @staticmethod
    def confirm_dedup_key(inn: Optional[str], email: str, campaign_id) -> str:
        """Канонический ключ идемпотентности решения: (ИНН, email, campaign)."""
        digits = "".join(ch for ch in str(inn or "") if ch.isdigit())
        return f"{digits}|{(email or '').strip().lower()}|{campaign_id or 0}"

    def confirm_submit(
        self, *, email: str, subject: str, body: str,
        inn: Optional[str] = None, campaign_id: Optional[int] = None,
        recipient_id: Optional[int] = None, message_id: Optional[int] = None,
        panel: Optional[dict] = None, status: str = "pending",
        reason: Optional[str] = None, kind: str = "outbound",
        in_reply_to: Optional[str] = None, thread_id: Optional[str] = None,
        dedup_key: Optional[str] = None,
    ) -> tuple[int, bool]:
        """Письмо в очередь подтверждений. Идемпотентно по dedup_key →
        (review_id, created?). status='skipped' — авто-скип на этапе очереди
        (suppression/90-дневный заслон) с причиной, для следа в логе.

        kind='reply' — ручной ответ автоответчика: message_id обычно None,
        in_reply_to/thread_id несут привязку к треду; dedup_key задаётся явно
        (по треду), т.к. campaign у ответа нет."""
        dedup = dedup_key or self.confirm_dedup_key(inn, email, campaign_id)
        now_iso = _now_iso()
        with self.transaction() as conn:
            cur = conn.execute(
                """
                INSERT INTO confirm_reviews
                    (dedup_key, campaign_id, recipient_id, message_id, inn, email,
                     subject, body, panel_json, status, reason,
                     kind, in_reply_to, thread_id,
                     decided_at, created_at, updated_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(dedup_key) DO NOTHING
                """,
                (
                    dedup, campaign_id, recipient_id, message_id,
                    ("".join(ch for ch in str(inn) if ch.isdigit()) or None)
                    if inn else None,
                    (email or "").strip().lower(), subject, body,
                    _json_dump(panel or {}),
                    status, reason,
                    kind, in_reply_to, thread_id,
                    now_iso if status != "pending" else None,
                    now_iso, now_iso,
                ),
            )
            if cur.rowcount == 1:
                return int(cur.lastrowid), True
            row = conn.execute(
                "SELECT id FROM confirm_reviews WHERE dedup_key=?", (dedup,)
            ).fetchone()
            return int(row["id"]), False

    def confirm_get(self, review_id: int) -> Optional[dict]:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM confirm_reviews WHERE id=?", (review_id,)
            ).fetchone()
        return _row_to_confirm(row) if row else None

    def confirm_get_by_key(
        self, inn: Optional[str], email: str, campaign_id
    ) -> Optional[dict]:
        dedup = self.confirm_dedup_key(inn, email, campaign_id)
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM confirm_reviews WHERE dedup_key=?", (dedup,)
            ).fetchone()
        return _row_to_confirm(row) if row else None

    def confirm_update_letter(self, review_id: int, *, subject: str,
                              body: str, panel: Optional[dict] = None) -> bool:
        """#71: заменить текст письма в PENDING-строке очереди (перегенерация).
        Решённые строки не трогаем — там уже есть история решения."""
        now_iso = _now_iso()
        with self.transaction() as conn:
            if panel is not None:
                cur = conn.execute(
                    "UPDATE confirm_reviews SET subject=?, body=?, "
                    "panel_json=?, updated_at=? WHERE id=? AND status='pending'",
                    (subject, body, _json_dump(panel), now_iso, int(review_id)))
            else:
                cur = conn.execute(
                    "UPDATE confirm_reviews SET subject=?, body=?, updated_at=? "
                    "WHERE id=? AND status='pending'",
                    (subject, body, now_iso, int(review_id)))
            return cur.rowcount > 0

    def confirm_find_reply_pending(self, *, email: str = "",
                                   thread_id: str = "") -> Optional[dict]:
        """Черновик ответа в очереди по лиду (#62): сперва точный тред, потом
        адрес. Только pending — решённые оператору не предлагаем."""
        email_l = (email or "").strip().lower()
        with self._lock:
            row = None
            if thread_id:
                row = self._conn.execute(
                    "SELECT id, subject, status, email FROM confirm_reviews "
                    "WHERE kind='reply' AND status='pending' AND thread_id=? "
                    "ORDER BY id DESC LIMIT 1", (thread_id,)).fetchone()
            if row is None and email_l:
                row = self._conn.execute(
                    "SELECT id, subject, status, email FROM confirm_reviews "
                    "WHERE kind='reply' AND status='pending' "
                    "AND LOWER(email)=? ORDER BY id DESC LIMIT 1",
                    (email_l,)).fetchone()
        return dict(row) if row else None

    def last_sent_mailbox(self) -> Optional[str]:
        """Ящик последней реальной отправки — указатель ротации ящиков (#59).
        Смотрим события sent/reply_sent (у обоих mailbox_id проставлен);
        durable: переживает рестарт службы, в отличие от указателя в памяти."""
        with self._lock:
            row = self._conn.execute(
                "SELECT mailbox_id FROM events "
                "WHERE event_type IN ('sent','reply_sent') "
                "AND COALESCE(mailbox_id,'')<>'' "
                "ORDER BY id DESC LIMIT 1").fetchone()
        return row["mailbox_id"] if row else None

    def sent_flags(self, *, inns: Optional[list] = None,
                   emails: Optional[list] = None) -> dict:
        """Батч-пометка «уже отправляли» для списков лидов/очереди (Фича 2).

        Один SELECT по всем inn/email страницы (не N+1). Возвращает
        {ключ → {ever, last_ts, replied, within_90d}}, где ключ — нормализ.
        ИНН (только цифры) и/или email (lower). within_90d — та же граница,
        что у стоп-флага recent_contact."""
        from datetime import datetime, timedelta, timezone
        inn_keys = {"".join(c for c in str(x) if c.isdigit())
                    for x in (inns or []) if x}
        email_keys = {str(x).strip().lower() for x in (emails or []) if x}
        if not inn_keys and not email_keys:
            return {}
        clauses, params = [], []
        if inn_keys:
            clauses.append(f"inn IN ({','.join('?' for _ in inn_keys)})")
            params += list(inn_keys)
        if email_keys:
            clauses.append(
                f"LOWER(email) IN ({','.join('?' for _ in email_keys)})")
            params += list(email_keys)
        with self._lock:
            rows = self._conn.execute(
                f"SELECT inn, email, ts, outcome FROM send_log "
                f"WHERE {' OR '.join(clauses)} ORDER BY ts ASC", params
            ).fetchall()
        border = (datetime.now(timezone.utc) - timedelta(days=90)).isoformat()
        out: dict = {}

        def _touch(key, ts, outcome):
            e = out.setdefault(key, {"ever": False, "last_ts": None,
                                     "replied": False, "within_90d": False})
            e["ever"] = True
            if e["last_ts"] is None or str(ts) > str(e["last_ts"]):
                e["last_ts"] = ts
            if outcome == "replied":
                e["replied"] = True
            if str(ts) >= border:
                e["within_90d"] = True

        for r in rows:
            digits = "".join(c for c in str(r["inn"] or "") if c.isdigit())
            if digits and digits in inn_keys:
                _touch(digits, r["ts"], r["outcome"])
            em = (r["email"] or "").strip().lower()
            if em and em in email_keys:
                _touch(em, r["ts"], r["outcome"])
        return out

    def confirm_set_panel(self, review_id: int, panel: dict) -> dict:
        """Перезаписать panel_json карточки (только pending).

        Нужен, чтобы выбор ящика оператором сохранялся там же, откуда его
        читает отправка (panel.mailbox_id), — без второго источника правды.
        """
        import json as _json
        with self.transaction() as conn:
            row = conn.execute(
                "SELECT status FROM confirm_reviews WHERE id=?", (review_id,)
            ).fetchone()
            if row is None:
                raise ValidationError(f"карточка {review_id} не найдена")
            if row["status"] != "pending":
                raise ValidationError(
                    f"правка карточки только для pending (сейчас {row['status']})")
            conn.execute(
                "UPDATE confirm_reviews SET panel_json=?, updated_at=? WHERE id=?",
                (_json.dumps(panel or {}, ensure_ascii=False), _now_iso(),
                 review_id))
        return self.confirm_get(review_id)

    def confirm_change_email(self, review_id: int, new_email: str) -> dict:
        """Сменить адрес получателя в карточке подтверждения (только pending).

        Пересчитывает dedup_key <inn>|<email>|<campaign>; если такой уже есть
        в очереди — ValidationError («уже в очереди»). Возвращает обновлённую
        карточку. Гейты (suppression/division/mx) сработают при отправке по
        НОВОМУ адресу — здесь не проверяются."""
        email = (new_email or "").strip().lower()
        if "@" not in email:
            raise ValidationError(f"невалидный email {new_email!r}")
        with self.transaction() as conn:
            row = conn.execute(
                "SELECT * FROM confirm_reviews WHERE id=?", (review_id,)
            ).fetchone()
            if row is None:
                raise ValidationError(f"карточка {review_id} не найдена")
            if row["status"] != "pending":
                raise ValidationError(
                    f"смена адреса только для pending (сейчас {row['status']})")
            new_dedup = self.confirm_dedup_key(
                row["inn"], email, row["campaign_id"])
            clash = conn.execute(
                "SELECT id FROM confirm_reviews WHERE dedup_key=? AND id<>?",
                (new_dedup, review_id)).fetchone()
            if clash is not None:
                raise ValidationError(
                    f"адрес {email} уже в очереди (карточка {clash['id']})")
            conn.execute(
                "UPDATE confirm_reviews SET email=?, dedup_key=?, updated_at=? "
                "WHERE id=?", (email, new_dedup, _now_iso(), review_id))
        return self.confirm_get(review_id)

    def confirm_list(
        self, *, status: Optional[str] = None, campaign_id: Optional[int] = None,
        limit: int = 50, offset: int = 0,
    ) -> list[dict]:
        sql = ["SELECT * FROM confirm_reviews WHERE 1=1"]
        params: list[Any] = []
        if status is not None:
            sql.append("AND status = ?")
            params.append(status)
        if campaign_id is not None:
            sql.append("AND campaign_id = ?")
            params.append(campaign_id)
        sql.append("ORDER BY id ASC LIMIT ? OFFSET ?")
        params.extend([int(limit), int(offset)])
        with self._lock:
            rows = self._conn.execute(" ".join(sql), params).fetchall()
        return [_row_to_confirm(r) for r in rows]

    def confirm_golden(self, *, limit: int = 500) -> list[dict]:
        """Золотые пары (правки оператора) НЕЗАВИСИМО от статуса. Критерий —
        сама правка (edited_body IS NOT NULL), а не status='edited': в
        live-режиме правленое письмо сразу становится 'sent', и фильтр по
        статусу терял именно боевые правки — выгрузка для анализа ошибок
        генерации была бы пустой (владелец 2026-07-24: обе версии письма
        должны быть доступны для разбора)."""
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM confirm_reviews WHERE edited_body IS NOT NULL "
                "ORDER BY id DESC LIMIT ?", (int(limit),)).fetchall()
        return [_row_to_confirm(r) for r in rows]

    def confirm_counts(self) -> dict:
        with self._lock:
            rows = self._conn.execute(
                "SELECT status, COUNT(*) c FROM confirm_reviews GROUP BY status"
            ).fetchall()
        return {r["status"]: int(r["c"]) for r in rows}

    def confirm_claim_sending(self, review_id: int) -> bool:
        """A4: атомарный захват review перед живой отправкой. True — захватили
        (было pending), False — уже решён/захвачен параллельным запросом.
        Пока 'sending_live', письмо не видно в pending-очереди и не может быть
        отправлено второй раз."""
        now_iso = _now_iso()
        with self.transaction() as conn:
            cur = conn.execute(
                "UPDATE confirm_reviews SET status='sending_live', updated_at=? "
                "WHERE id=? AND status='pending'", (now_iso, review_id))
            return cur.rowcount == 1

    def confirm_release_sending(self, review_id: int) -> None:
        """A4: отправка сорвалась (SMTP/гейт) — вернуть письмо на решение."""
        now_iso = _now_iso()
        with self.transaction() as conn:
            conn.execute(
                "UPDATE confirm_reviews SET status='pending', updated_at=? "
                "WHERE id=? AND status='sending_live'", (now_iso, review_id))

    def confirm_decide(
        self, review_id: int, *, status: str, reason: Optional[str] = None,
        edited_subject: Optional[str] = None, edited_body: Optional[str] = None,
        diff_text: Optional[str] = None, decided_by: str = "",
    ) -> bool:
        """Зафиксировать решение оператора. Идемпотентно: уже решённый review
        не перерешивается (возврат False). Решение и перевод письма в
        messages — ОДНА транзакция (решение без письма/письмо без решения
        невозможны). approved|edited → messages.status='scheduled' (+правки
        текста при edited); skipped|stoplist → messages skipped.

        status='sent' — письмо УЖЕ отправлено вживую через sender.send()
        (ручной immediate-send): messages не трогаем (там уже 'sent'), только
        фиксируем решение review для аудита/золотых пар."""
        if status not in ("approved", "edited", "skipped", "stoplist", "sent"):
            raise ValidationError(f"confirm_decide: недопустимый статус {status!r}")
        now_iso = _now_iso()
        with self.transaction() as conn:
            row = conn.execute(
                "SELECT * FROM confirm_reviews WHERE id=?", (review_id,)
            ).fetchone()
            if row is None:
                raise StoreError(f"confirm review not found: {review_id}")
            if row["status"] not in ("pending", "sending_live"):
                return False  # уже решено — решение неизменно (аудит-след)
            conn.execute(
                """UPDATE confirm_reviews
                      SET status=?, reason=?, edited_subject=?, edited_body=?,
                          diff_text=?, decided_by=?, decided_at=?, updated_at=?
                    WHERE id=?""",
                (status, reason, edited_subject, edited_body, diff_text,
                 decided_by, now_iso, now_iso, review_id),
            )
            mid = row["message_id"]
            if mid is not None:
                if status == "sent":
                    pass  # письмо уже sent через sender.send(): не трогаем
                elif status in ("approved", "edited"):
                    subj = edited_subject if status == "edited" and edited_subject \
                        else row["subject"]
                    body = edited_body if status == "edited" and edited_body \
                        else row["body"]
                    conn.execute(
                        """UPDATE messages
                              SET status='scheduled', subject=?, body_rendered=?,
                                  updated_at=?
                            WHERE id=? AND status NOT IN ('sent','skipped','failed')""",
                        (subj, body, now_iso, mid),
                    )
                else:
                    conn.execute(
                        # Ревью №2: раньше фильтр был строго 'pending_review',
                        # и «скип» по письму, уехавшему в 'scheduled' из-за
                        # временной ошибки SMTP, молча не применялся —
                        # confirm_decide при этом возвращал True. Решение
                        # оператора должно побеждать в любом нетерминальном статусе.
                        """UPDATE messages
                              SET status='skipped', last_error=?, updated_at=?
                            WHERE id=? AND status NOT IN ('sent','skipped','failed')""",
                        (f"confirm:{status}:{reason or ''}", now_iso, mid),
                    )
        return True

    # -- send_log: история контактов (Задача 3) ----------------------------- #

    def send_log_add(
        self, *, email: str, outcome: str = "sent", inn: Optional[str] = None,
        campaign_id: Optional[int] = None, ts: Optional[datetime] = None,
        message_id: Optional[int] = None, rfc_message_id: Optional[str] = None,
        subject: Optional[str] = None,
    ) -> int:
        now_iso = _now_iso()
        ts_iso = _to_iso(ts) if ts is not None else now_iso
        digits = "".join(ch for ch in str(inn or "") if ch.isdigit()) or None
        with self.transaction() as conn:
            cur = conn.execute(
                """INSERT INTO send_log
                       (inn, email, campaign_id, ts, message_id, rfc_message_id,
                        subject, outcome, created_at)
                   VALUES (?,?,?,?,?,?,?,?,?)""",
                (digits, (email or "").strip().lower(), campaign_id, ts_iso,
                 message_id, rfc_message_id, subject, outcome, now_iso),
            )
            return int(cur.lastrowid)

    def send_log_history(
        self, *, email: Optional[str] = None, inn: Optional[str] = None,
        limit: int = 10,
    ) -> list[dict]:
        """История контактов по email И/ИЛИ ИНН (объединение), новые первыми."""
        clauses, params = [], []
        if email:
            clauses.append("email = ?")
            params.append(email.strip().lower())
        if inn:
            digits = "".join(ch for ch in str(inn) if ch.isdigit())
            if digits:
                clauses.append("inn = ?")
                params.append(digits)
        if not clauses:
            return []
        sql = (f"SELECT * FROM send_log WHERE {' OR '.join(clauses)}"
               " ORDER BY ts DESC, id DESC LIMIT ?")
        params.append(int(limit))
        with self._lock:
            rows = self._conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]

    def last_contact(
        self, *, email: Optional[str] = None, inn: Optional[str] = None
    ) -> Optional[dict]:
        """Последняя ОТПРАВКА (outcome='sent') на этот email/ИНН."""
        rows = self.send_log_history(email=email, inn=inn, limit=50)
        for r in rows:
            if r.get("outcome") == "sent":
                return r
        return None

    # -- BUILD-NEW: lead-desk (Фаза 2.1) ----------------------------------- #

    def create_lead(self, *, email: str, dedup_key: str, recipient_id=None,
                    campaign_id=None, thread_id=None, company_name=None, inn=None,
                    reply_kind=None, phone=None, need=None, readiness=None,
                    source_event_id=None, sla_due_at=None) -> tuple[int, bool]:
        """Создать лид идемпотентно (ON CONFLICT(dedup_key)). → (lead_id, created?)."""
        now_iso = _now_iso()
        with self.transaction() as conn:
            cur = conn.execute(
                """INSERT INTO leads
                    (recipient_id, campaign_id, thread_id, email, company_name, inn,
                     status, reply_kind, phone, need, readiness, source_event_id,
                     dedup_key, sla_due_at, version, created_at, updated_at)
                   VALUES (?,?,?,?,?,?, 'new', ?,?,?,?,?, ?,?, 0, ?,?)
                   ON CONFLICT(dedup_key) DO NOTHING""",
                (recipient_id, campaign_id, thread_id, email.strip().lower(),
                 company_name, inn, reply_kind, phone, need, readiness,
                 source_event_id, dedup_key, _to_iso(sla_due_at), now_iso, now_iso),
            )
            if cur.rowcount == 1:
                lead_id = int(cur.lastrowid)
                conn.execute(
                    "INSERT INTO lead_events (lead_id, action, to_status, created_at)"
                    " VALUES (?, 'created', 'new', ?)", (lead_id, now_iso))
                return lead_id, True
            row = conn.execute(
                "SELECT id FROM leads WHERE dedup_key=?", (dedup_key,)).fetchone()
            return int(row["id"]), False

    def get_lead(self, lead_id: int) -> Optional["Lead"]:
        with self._lock:
            row = self._conn.execute("SELECT * FROM leads WHERE id=?", (lead_id,)).fetchone()
        return _row_to_lead(row) if row else None

    def list_leads(self, *, status=None, assigned_to=None, unassigned=False,
                   reply_kind=None, limit: int = 100, offset: int = 0) -> list["Lead"]:
        sql = ["SELECT * FROM leads WHERE 1=1"]
        params: list[Any] = []
        if status is not None:
            vals = status if isinstance(status, (list, tuple, set)) else [status]
            sql.append("AND status IN (%s)" % ",".join("?" for _ in vals))
            params.extend(vals)
        if unassigned:
            sql.append("AND assigned_to IS NULL")
        elif assigned_to is not None:
            sql.append("AND assigned_to = ?")
            params.append(assigned_to)
        if reply_kind is not None:
            sql.append("AND reply_kind = ?")
            params.append(reply_kind)
        sql.append("ORDER BY created_at DESC, id DESC LIMIT ? OFFSET ?")
        params.extend([int(limit), int(offset)])
        with self._lock:
            rows = self._conn.execute(" ".join(sql), params).fetchall()
        return [_row_to_lead(r) for r in rows]

    def update_lead_cas(self, lead_id: int, *, expected_version: int,
                        actor_user_id=None, action: str = "status_changed",
                        **fields) -> Optional["Lead"]:
        """Оптимистичная блокировка: UPDATE ... WHERE id=? AND version=?.
        Возвращает обновлённый Lead или None при конфликте версий (кто-то уже
        изменил лид). Пишет lead_events. fields: status/assigned_to/phone/need/
        readiness/bitrix_lead_id/reply_kind."""
        allowed = {"status", "assigned_to", "phone", "need", "readiness",
                   "bitrix_lead_id", "reply_kind", "company_name", "inn"}
        sets = {k: v for k, v in fields.items() if k in allowed}
        now_iso = _now_iso()
        with self.transaction() as conn:
            cur_row = conn.execute(
                "SELECT status, version FROM leads WHERE id=?", (lead_id,)).fetchone()
            if cur_row is None:
                return None
            from_status = cur_row["status"]
            cols = ", ".join(f"{k}=?" for k in sets)
            cols = (cols + ", " if cols else "") + "version=version+1, updated_at=?"
            params = [*sets.values(), now_iso, lead_id, expected_version]
            cur = conn.execute(
                f"UPDATE leads SET {cols} WHERE id=? AND version=?", params)
            if cur.rowcount == 0:
                return None  # конфликт версий
            conn.execute(
                """INSERT INTO lead_events
                    (lead_id, actor_user_id, action, from_status, to_status,
                     detail_json, created_at) VALUES (?,?,?,?,?,?,?)""",
                (lead_id, actor_user_id, action, from_status,
                 sets.get("status", from_status), _json_dump(sets), now_iso))
            row = conn.execute("SELECT * FROM leads WHERE id=?", (lead_id,)).fetchone()
        return _row_to_lead(row)

    def list_lead_events(self, lead_id: int) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT actor_user_id, action, from_status, to_status, detail_json,"
                " created_at FROM lead_events WHERE lead_id=? ORDER BY created_at ASC, id ASC",
                (lead_id,)).fetchall()
        return [{"actor_user_id": r["actor_user_id"], "action": r["action"],
                 "from_status": r["from_status"], "to_status": r["to_status"],
                 "detail": _json_load(r["detail_json"]), "created_at": r["created_at"]}
                for r in rows]

    def lead_stats(self) -> dict:
        with self._lock:
            by_status = {r["status"]: int(r["c"]) for r in self._conn.execute(
                "SELECT status, COUNT(*) c FROM leads GROUP BY status").fetchall()}
            total = sum(by_status.values())
            overdue = int(self._conn.execute(
                "SELECT COUNT(*) c FROM leads WHERE sla_due_at IS NOT NULL "
                "AND sla_due_at < ? AND status IN ('new','assigned')",
                (_now_iso(),)).fetchone()["c"])
        return {"total": total, "by_status": by_status, "sla_overdue": overdue}

    # -- BUILD-NEW: auth (users/sessions) ---------------------------------- #

    def create_user(self, *, username: str, password_hash: str, role: str = "manager",
                    email=None, totp_secret=None) -> int:
        now_iso = _now_iso()
        with self.transaction() as conn:
            cur = conn.execute(
                """INSERT INTO users (username, email, password_hash, role,
                    totp_secret, is_active, created_at, updated_at)
                   VALUES (?,?,?,?,?,1,?,?)""",
                (username, email, password_hash, role, totp_secret, now_iso, now_iso))
            return int(cur.lastrowid)

    def get_user(self, user_id: int) -> Optional["User"]:
        with self._lock:
            row = self._conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
        return _row_to_user(row) if row else None

    def get_user_by_username(self, username: str) -> Optional["User"]:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM users WHERE username=?", (username,)).fetchone()
        return _row_to_user(row) if row else None

    def list_users(self) -> list["User"]:
        with self._lock:
            rows = self._conn.execute("SELECT * FROM users ORDER BY id").fetchall()
        return [_row_to_user(r) for r in rows]

    def update_user(self, user_id: int, **fields) -> None:
        allowed = {"password_hash", "role", "totp_secret", "is_active", "email"}
        sets = {k: (int(v) if k == "is_active" else v)
                for k, v in fields.items() if k in allowed}
        if not sets:
            return
        cols = ", ".join(f"{k}=?" for k in sets)
        with self.transaction() as conn:
            conn.execute(f"UPDATE users SET {cols}, updated_at=? WHERE id=?",
                         [*sets.values(), _now_iso(), user_id])

    def create_session(self, *, user_id: int, token_hash: str, expires_at: datetime,
                       user_agent=None, ip=None) -> int:
        with self.transaction() as conn:
            cur = conn.execute(
                """INSERT INTO sessions (user_id, token_hash, created_at, expires_at,
                    revoked, user_agent, ip) VALUES (?,?,?,?,0,?,?)""",
                (user_id, token_hash, _now_iso(), _to_iso(expires_at), user_agent, ip))
            return int(cur.lastrowid)

    def get_session_by_token(self, token_hash: str) -> Optional["Session"]:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM sessions WHERE token_hash=?", (token_hash,)).fetchone()
        return _row_to_session(row) if row else None

    def revoke_session(self, token_hash: str) -> None:
        with self.transaction() as conn:
            conn.execute("UPDATE sessions SET revoked=1 WHERE token_hash=?", (token_hash,))

    def revoke_user_sessions(self, user_id: int) -> None:
        with self.transaction() as conn:
            conn.execute("UPDATE sessions SET revoked=1 WHERE user_id=?", (user_id,))

    def change_password_and_revoke(self, user_id: int, password_hash: str) -> None:
        """Смена пароля и отзыв ВСЕХ сессий одной транзакцией (ревью,
        подтверждено): при падении между двумя отдельными вызовами старые
        сессии оставались валидными с уже сменённым паролем."""
        now_iso = _now_iso()
        with self.transaction() as conn:
            cur = conn.execute(
                "UPDATE users SET password_hash=?, updated_at=? WHERE id=?",
                (password_hash, now_iso, user_id))
            if cur.rowcount == 0:
                raise StoreError(f"user not found: {user_id}")
            conn.execute("UPDATE sessions SET revoked=1 WHERE user_id=?",
                         (user_id,))

    # -- auth-throttle: защита от перебора (ревью, подтверждено) ------------ #

    def auth_throttle_state(self, username: str) -> dict:
        """{'failed': N, 'locked_until': datetime|None} по username."""
        with self._lock:
            row = self._conn.execute(
                "SELECT failed, locked_until FROM auth_throttle WHERE username=?",
                ((username or "").strip().lower(),)).fetchone()
        if row is None:
            return {"failed": 0, "locked_until": None}
        return {"failed": int(row["failed"]),
                "locked_until": _from_iso(row["locked_until"])}

    def auth_throttle_bump(
        self, username: str, *, success: bool,
        lock_after: int = 5, base_lock_sec: int = 30, max_lock_sec: int = 3600,
    ) -> None:
        """Успех — сброс счётчика; неуспех — инкремент и экспоненциальный лок
        после lock_after подряд (30с * 2^k, потолок max_lock_sec)."""
        uname = (username or "").strip().lower()
        now_iso = _now_iso()
        with self.transaction() as conn:
            if success:
                conn.execute("DELETE FROM auth_throttle WHERE username=?", (uname,))
                return
            row = conn.execute(
                "SELECT failed FROM auth_throttle WHERE username=?", (uname,)
            ).fetchone()
            failed = (int(row["failed"]) if row else 0) + 1
            locked_until = None
            if failed >= lock_after:
                lock_sec = min(max_lock_sec,
                               base_lock_sec * (2 ** (failed - lock_after)))
                locked_until = _to_iso(_now() + timedelta(seconds=lock_sec))
            conn.execute(
                """INSERT INTO auth_throttle (username, failed, locked_until, updated_at)
                   VALUES (?,?,?,?)
                   ON CONFLICT(username) DO UPDATE SET
                       failed=excluded.failed, locked_until=excluded.locked_until,
                       updated_at=excluded.updated_at""",
                (uname, failed, locked_until, now_iso))

    # -- BUILD-NEW: audit-лог действий ------------------------------------- #

    def get_setting(self, key: str, default=None):
        """Настройка панели (panel_settings). JSON-декодит значение; default при отсутствии."""
        with self._lock:
            row = self._conn.execute(
                "SELECT value FROM panel_settings WHERE key=?", (key,)).fetchone()
        if row is None or row[0] is None:
            return default
        try:
            return json.loads(row[0])
        except Exception:  # noqa: BLE001 - не-JSON храним как строку
            return row[0]

    def set_setting(self, key: str, value) -> None:
        """Записать настройку панели (JSON-энкод). None удаляет ключ."""
        with self._lock, self._conn:
            if value is None:
                self._conn.execute("DELETE FROM panel_settings WHERE key=?", (key,))
                return
            self._conn.execute(
                "INSERT INTO panel_settings(key, value, updated_at) VALUES(?,?,?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value, "
                "updated_at=excluded.updated_at",
                (key, json.dumps(value, ensure_ascii=False), _now_iso()))

    def append_audit(self, *, action: str, actor_user_id=None, entity_type=None,
                     entity_id=None, detail=None, ip=None) -> int:
        with self.transaction() as conn:
            cur = conn.execute(
                """INSERT INTO audit_log (actor_user_id, action, entity_type,
                    entity_id, detail_json, ip, created_at) VALUES (?,?,?,?,?,?,?)""",
                (actor_user_id, action, entity_type,
                 None if entity_id is None else str(entity_id),
                 _json_dump(detail or {}), ip, _now_iso()))
            return int(cur.lastrowid)

    def list_audit(self, *, actor_user_id=None, action=None, limit: int = 200,
                   offset: int = 0) -> list[dict]:
        sql = ["SELECT * FROM audit_log WHERE 1=1"]
        params: list[Any] = []
        if actor_user_id is not None:
            sql.append("AND actor_user_id = ?")
            params.append(actor_user_id)
        if action is not None:
            sql.append("AND action = ?")
            params.append(action)
        sql.append("ORDER BY created_at DESC, id DESC LIMIT ? OFFSET ?")
        params.extend([int(limit), int(offset)])
        with self._lock:
            rows = self._conn.execute(" ".join(sql), params).fetchall()
        return [{"id": int(r["id"]), "actor_user_id": r["actor_user_id"],
                 "action": r["action"], "entity_type": r["entity_type"],
                 "entity_id": r["entity_id"], "detail": _json_load(r["detail_json"]),
                 "ip": r["ip"], "created_at": r["created_at"]} for r in rows]


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


def _row_to_lead(row: sqlite3.Row) -> Lead:
    return Lead(
        id=int(row["id"]),
        recipient_id=row["recipient_id"],
        campaign_id=row["campaign_id"],
        thread_id=row["thread_id"],
        email=row["email"],
        company_name=row["company_name"],
        inn=row["inn"],
        status=row["status"],
        reply_kind=row["reply_kind"],
        phone=row["phone"],
        need=row["need"],
        readiness=row["readiness"],
        assigned_to=row["assigned_to"],
        source_event_id=row["source_event_id"],
        bitrix_lead_id=row["bitrix_lead_id"],
        dedup_key=row["dedup_key"],
        sla_due_at=_from_iso(row["sla_due_at"]),
        version=int(row["version"]),
        created_at=_from_iso(row["created_at"]),  # type: ignore[arg-type]
        updated_at=_from_iso(row["updated_at"]),  # type: ignore[arg-type]
    )


def _row_to_user(row: sqlite3.Row) -> User:
    return User(
        id=int(row["id"]),
        username=row["username"],
        email=row["email"],
        password_hash=row["password_hash"],
        role=row["role"],
        totp_secret=row["totp_secret"],
        is_active=bool(row["is_active"]),
        created_at=_from_iso(row["created_at"]),  # type: ignore[arg-type]
        updated_at=_from_iso(row["updated_at"]),  # type: ignore[arg-type]
    )


def _row_to_session(row: sqlite3.Row) -> Session:
    return Session(
        id=int(row["id"]),
        user_id=int(row["user_id"]),
        token_hash=row["token_hash"],
        created_at=_from_iso(row["created_at"]),  # type: ignore[arg-type]
        expires_at=_from_iso(row["expires_at"]),  # type: ignore[arg-type]
        revoked=bool(row["revoked"]),
        user_agent=row["user_agent"],
        ip=row["ip"],
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
        priority_max=(None if row["priority_max"] is None else int(row["priority_max"])),
        priority_total=(None if row["priority_total"] is None else float(row["priority_total"])),
        pxr=(None if row["pxr"] is None else float(row["pxr"])),
        region=row["region"],
        tz=row["tz"],
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


def _row_to_confirm(row: sqlite3.Row) -> dict:
    """confirm_reviews → dict (panel_json уже распакован)."""
    d = dict(row)
    d["panel"] = _json_load(d.pop("panel_json", None))
    return d


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
