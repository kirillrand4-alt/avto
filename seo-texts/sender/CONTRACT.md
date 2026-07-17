# Контракт интерфейсов — сендер «Руспром» (замена coldy)

Единый хребет для независимой разработки 12 модулей. Слои общаются только через типы из §3 и API из §2. Реализация не описывается — только контракт.

Общие правила:
- Все времена — UTC, храним ISO-8601 в `TEXT` (SQLite) или `int` epoch-секунды в счётчиках дня.
- Идентификаторы `id` — `INTEGER PRIMARY KEY AUTOINCREMENT`, если не указано иное.
- Идемпотентность строится на `UNIQUE`-ключах, а не на «проверил-потом-вставил».
- Модули не пишут в чужие таблицы напрямую — только через `store`.

---

## 1. SQLite-схема

Прагмы (задаёт `store` при открытии): `PRAGMA journal_mode=WAL; PRAGMA foreign_keys=ON; PRAGMA busy_timeout=5000; PRAGMA synchronous=NORMAL;`

### recipients
```sql
CREATE TABLE recipients (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    inn           TEXT,                      -- ИНН юрлица (может быть NULL до обогащения)
    email         TEXT NOT NULL,
    domain        TEXT NOT NULL,             -- нормализованный домен из email
    company_name  TEXT,
    okved         TEXT,                      -- код ОКВЭД → выбор оборудования
    segment       TEXT,                      -- сегмент из bitrix (чек/категория)
    bitrix_id     TEXT,
    contact_name  TEXT,                      -- реальное имя (AI/парсинг), может быть NULL
    mx_provider   TEXT,                      -- yandex|mailru|google|outlook|other|unknown
    valid_status  TEXT NOT NULL DEFAULT 'unknown',  -- unknown|valid|invalid|risky
    catch_all     INTEGER,                   -- 0/1/NULL
    role_based    INTEGER,                   -- 0/1/NULL (info@, sales@…)
    disposable    INTEGER,                   -- 0/1/NULL
    source        TEXT,                      -- откуда лид
    extra_json    TEXT,                      -- произвольные merge-поля (JSON)
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL
);
CREATE UNIQUE INDEX ux_recipients_email ON recipients(email);
CREATE INDEX ix_recipients_domain   ON recipients(domain);
CREATE INDEX ix_recipients_inn      ON recipients(inn);
CREATE INDEX ix_recipients_provider ON recipients(mx_provider);
CREATE INDEX ix_recipients_valid    ON recipients(valid_status);
```
`UNIQUE(email)` — дедуп базы на уровне БД.

### campaigns
```sql
CREATE TABLE campaigns (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    name           TEXT NOT NULL,
    status         TEXT NOT NULL DEFAULT 'draft',  -- draft|active|paused|stopped|done
    legal_entity   TEXT NOT NULL,   -- "ООО Руспром"
    legal_inn      TEXT NOT NULL,   -- ИНН Руспром в тело письма-1
    provider_pool  TEXT,            -- имя пула провайдер-сплита (см. конфиг)
    config_json    TEXT,            -- снапшот параметров кампании
    created_at     TEXT NOT NULL,
    started_at     TEXT,
    paused_at      TEXT,
    updated_at     TEXT NOT NULL
);
CREATE INDEX ix_campaigns_status ON campaigns(status);
```

### sequence_steps
```sql
CREATE TABLE sequence_steps (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    campaign_id    INTEGER NOT NULL REFERENCES campaigns(id) ON DELETE CASCADE,
    step_index     INTEGER NOT NULL,     -- 0,1,2…
    delay_hours    INTEGER NOT NULL,     -- задержка от предыдущего касания
    subject_tmpl   TEXT NOT NULL,
    body_tmpl      TEXT NOT NULL,
    engagement_gate TEXT NOT NULL DEFAULT 'all', -- all|not_bounced|engaged
    include_legal  INTEGER NOT NULL DEFAULT 0,    -- 1 для письма-1 (атрибуция+ИНН)
    active         INTEGER NOT NULL DEFAULT 1,
    created_at     TEXT NOT NULL
);
CREATE UNIQUE INDEX ux_step_campaign_idx ON sequence_steps(campaign_id, step_index);
```

### messages
Центральная таблица очереди/истории. Идемпотентность отправки.
```sql
CREATE TABLE messages (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    idempotency_key  TEXT NOT NULL,   -- sha256(campaign_id|recipient_id|step_index)
    campaign_id      INTEGER NOT NULL REFERENCES campaigns(id),
    recipient_id     INTEGER NOT NULL REFERENCES recipients(id),
    sequence_step_id INTEGER NOT NULL REFERENCES sequence_steps(id),
    mailbox_id       TEXT,            -- какой ящик назначен (NULL до планирования)
    status           TEXT NOT NULL DEFAULT 'pending',
        -- pending|scheduled|sending|sent|failed|skipped|suppressed
    scheduled_at     TEXT,            -- когда планово слать
    claimed_at       TEXT,            -- lease-метка воркера (резюм)
    sent_at          TEXT,
    rfc_message_id   TEXT,            -- Message-ID:, генерим до отправки
    in_reply_to      TEXT,           -- для тредов цепочки
    thread_id        TEXT,           -- корреляция касаний одного получателя/кампании
    subject          TEXT,
    body_rendered    TEXT,
    unsub_token      TEXT,            -- токен one-click для List-Unsubscribe
    attempt_count    INTEGER NOT NULL DEFAULT 0,
    last_error       TEXT,
    created_at       TEXT NOT NULL,
    updated_at       TEXT NOT NULL
);
CREATE UNIQUE INDEX ux_messages_idem   ON messages(idempotency_key);
CREATE UNIQUE INDEX ux_messages_rfcid  ON messages(rfc_message_id) WHERE rfc_message_id IS NOT NULL;
CREATE INDEX ix_messages_status_sched  ON messages(status, scheduled_at);
CREATE INDEX ix_messages_mailbox       ON messages(mailbox_id, status);
CREATE INDEX ix_messages_recipient     ON messages(recipient_id);
CREATE INDEX ix_messages_thread        ON messages(thread_id);
CREATE INDEX ix_messages_campaign      ON messages(campaign_id, status);
```
Идемпотентность: `ux_messages_idem` не даёт создать второе касание того же шага тому же получателю. Резюм: воркер берёт строки `status IN ('scheduled') AND scheduled_at<=now` c пустым/протухшим `claimed_at`, ставит `sending`+`claimed_at` в транзакции (lease). После рестарта «зависшие» `sending` со старым `claimed_at` возвращаются в `scheduled` (см. `store.recover_stale`).

### events
Append-only журнал. Источник правды для аналитики и гейтов.
```sql
CREATE TABLE events (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    dedup_key    TEXT NOT NULL,       -- уникальный ключ события (см. ниже)
    event_type   TEXT NOT NULL,       -- queued|sent|delivered|bounce|complaint|reply|
                                      -- unsubscribe|dsn|open|skip|suppress|error
    message_id   INTEGER REFERENCES messages(id),
    recipient_id INTEGER REFERENCES recipients(id),
    campaign_id  INTEGER REFERENCES campaigns(id),
    mailbox_id   TEXT,
    provider     TEXT,
    event_ts     TEXT NOT NULL,
    detail_json  TEXT,                -- сырьё DSN/жалобы/тред-ссылка
    created_at   TEXT NOT NULL
);
CREATE UNIQUE INDEX ux_events_dedup ON events(dedup_key);
CREATE INDEX ix_events_type_ts   ON events(event_type, event_ts);
CREATE INDEX ix_events_recipient ON events(recipient_id, event_type);
CREATE INDEX ix_events_campaign  ON events(campaign_id, event_type);
CREATE INDEX ix_events_mailbox   ON events(mailbox_id, event_type, event_ts);
```
`dedup_key` формируется источником: для IMAP — `imap:{uidvalidity}:{uid}:{event_type}`; для SMTP-send — `send:{message_id}`. `ON CONFLICT(dedup_key) DO NOTHING` гарантирует, что повторный поллинг IMAP не задваивает события.

### suppression
```sql
CREATE TABLE suppression (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    scope      TEXT NOT NULL,   -- email|domain|inn
    value      TEXT NOT NULL,   -- нормализованное значение
    reason     TEXT NOT NULL,   -- competitor|unsubscribe|complaint|bounce_hard|manual|dsn
    source     TEXT,
    campaign_id INTEGER,        -- NULL = глобально
    created_at TEXT NOT NULL,
    expires_at TEXT             -- NULL = навсегда
);
CREATE UNIQUE INDEX ux_suppression_scope_val ON suppression(scope, value);
CREATE INDEX ix_suppression_reason ON suppression(reason);
```

### mailbox_state
Дневные счётчики и статус ящика. Пересчёт дня — по `day_key`.
```sql
CREATE TABLE mailbox_state (
    mailbox_id     TEXT PRIMARY KEY,   -- логин ящика
    provider       TEXT NOT NULL,      -- yandex|mailru|google|outlook
    day_key        TEXT NOT NULL,      -- 'YYYY-MM-DD' в TZ конфига
    sent_today     INTEGER NOT NULL DEFAULT 0,
    sent_total     INTEGER NOT NULL DEFAULT 0,
    ramp_day       INTEGER NOT NULL DEFAULT 0,  -- день рампа для лимита
    daily_limit    INTEGER NOT NULL,            -- текущий лимит (из рамп-кривой)
    last_sent_at   TEXT,
    paused         INTEGER NOT NULL DEFAULT 0,
    pause_reason   TEXT,               -- gate_bounce|gate_complaint|manual|window
    updated_at     TEXT NOT NULL
);
CREATE INDEX ix_mailbox_paused ON mailbox_state(paused);
```
Резюм: счётчики персистентны, при рестарте не обнуляются; смена `day_key` сбрасывает `sent_today` и инкрементит `ramp_day` (атомарно в `store`).

### warmup_state
Свой живой прогрев (не пул).
```sql
CREATE TABLE warmup_state (
    mailbox_id       TEXT PRIMARY KEY REFERENCES mailbox_state(mailbox_id),
    phase            TEXT NOT NULL DEFAULT 'ramp',  -- ramp|steady|paused
    ramp_day         INTEGER NOT NULL DEFAULT 0,
    warmup_target    INTEGER NOT NULL DEFAULT 0,    -- целевой объём прогрева на сегодня
    warmup_sent_today INTEGER NOT NULL DEFAULT 0,
    reputation_score REAL,               -- 0..1, эвристика по bounce/reply прогрева
    day_key          TEXT NOT NULL,
    last_warmup_at   TEXT,
    updated_at       TEXT NOT NULL
);
```

---

## 2. Публичный API модулей

Только сигнатуры. Типы данных — из §3. Общий базовый класс исключений:

```python
class SenderError(Exception): ...
class ConfigError(SenderError): ...
class StoreError(SenderError): ...
class SuppressedError(SenderError): ...          # получатель под suppression
class ValidationError(SenderError): ...
class PersonalizationGateError(SenderError): ...  # незаполненные {}
class SendError(SenderError): ...
class RateLimitExceeded(SendError): ...
class GateTrippedError(SenderError): ...          # kill-switch сработал
class TransientError(SenderError): ...            # ретраибельно
```

### config
```python
class Config:
    """Загружает + валидирует YAML/env. Иммутабелен после load()."""

    @classmethod
    def load(cls, path: str | Path, env: Mapping[str, str] | None = None) -> "Config": ...
        # raises ConfigError при невалидной схеме/отсутствующих секретах

    def mailboxes(self) -> list[MailboxCfg]: ...
    def provider_pools(self) -> dict[str, list[str]]: ...   # pool_name -> [mailbox_id]
    def ramp_curve(self, provider: str) -> list[int]: ...    # индекс = ramp_day
    def sending_window(self) -> WindowCfg: ...
    def holidays(self) -> set[date]: ...
    def gates(self) -> GatesCfg: ...
    def legal(self) -> LegalCfg: ...                         # Руспром + ИНН + unsub base_url
    def get(self, dotted_key: str, default: Any = ...) -> Any: ...
```

### store
DAL. Единственный писатель в БД. Все методы идемпотентны, где это осмысленно.
```python
class Store:
    def __init__(self, db_path: str | Path): ...
    def init_schema(self) -> None: ...                       # CREATE IF NOT EXISTS + PRAGMA
    def recover_stale(self, lease_ttl_sec: int) -> int: ...  # 'sending'→'scheduled', вернёт кол-во

    # recipients
    def upsert_recipient(self, r: RecipientIn) -> int: ...          # ON CONFLICT(email)
    def bulk_upsert_recipients(self, rows: Iterable[RecipientIn]) -> int: ...
    def get_recipient(self, recipient_id: int) -> Recipient | None: ...
    def iter_recipients(self, *, valid_status: str | None = None,
                        provider: str | None = None) -> Iterator[Recipient]: ...

    # campaigns / steps
    def create_campaign(self, c: CampaignIn) -> int: ...
    def get_campaign(self, campaign_id: int) -> Campaign | None: ...
    def set_campaign_status(self, campaign_id: int, status: str) -> None: ...
    def add_step(self, s: SequenceStepIn) -> int: ...
    def get_steps(self, campaign_id: int) -> list[SequenceStep]: ...

    # messages (очередь)
    def enqueue_message(self, m: MessageIn) -> tuple[int, bool]: ...
        # ON CONFLICT(idempotency_key) DO NOTHING → (message_id, created?)
    def claim_due_messages(self, *, now: datetime, mailbox_ids: Sequence[str],
                           limit: int) -> list[Message]: ...
        # атомарно 'scheduled'→'sending'+claimed_at; только due и не под suppression
    def mark_sent(self, message_id: int, rfc_message_id: str, sent_at: datetime) -> None: ...
    def mark_failed(self, message_id: int, error: str, *, retryable: bool) -> None: ...
    def mark_skipped(self, message_id: int, reason: str) -> None: ...
    def get_message(self, message_id: int) -> Message | None: ...
    def find_message_by_rfc_id(self, rfc_message_id: str) -> Message | None: ...

    # events (append-only)
    def append_event(self, e: EventIn) -> tuple[int, bool]: ...   # ON CONFLICT(dedup_key)
    def count_events(self, *, event_type: str, campaign_id: int | None = None,
                     domain: str | None = None, since: datetime | None = None) -> int: ...
    def has_reply(self, recipient_id: int, campaign_id: int) -> bool: ...

    # suppression
    def suppression_lookup(self, *, email: str, domain: str, inn: str | None) -> SuppressionEntry | None: ...
    def suppression_add(self, e: SuppressionIn) -> tuple[int, bool]: ...

    # mailbox / warmup state
    def get_mailbox_state(self, mailbox_id: str) -> MailboxState | None: ...
    def upsert_mailbox_state(self, s: MailboxState) -> None: ...
    def increment_sent(self, mailbox_id: str, *, now: datetime) -> MailboxState: ...  # атомарно
    def set_mailbox_paused(self, mailbox_id: str, paused: bool, reason: str | None) -> None: ...
    def get_warmup_state(self, mailbox_id: str) -> WarmupState | None: ...
    def upsert_warmup_state(self, s: WarmupState) -> None: ...

    def transaction(self) -> AbstractContextManager: ...     # BEGIN IMMEDIATE
    def close(self) -> None: ...
```

### suppression
```python
class Suppression:
    def __init__(self, store: Store): ...
    def is_suppressed(self, recipient: Recipient) -> SuppressionEntry | None: ...
        # проверяет email → domain → inn
    def add_email(self, email: str, reason: str, *, source: str = "", campaign_id: int | None = None) -> bool: ...
    def add_domain(self, domain: str, reason: str, *, source: str = "") -> bool: ...
    def add_inn(self, inn: str, reason: str, *, source: str = "") -> bool: ...
    def import_competitors(self, values: Iterable[str], scope: str = "domain") -> int: ...
```

### validation
```python
class Validation:
    def __init__(self, config: Config): ...
    def validate(self, email: str) -> ValidationResult: ...        # MX+provider+catch_all…
    def validate_batch(self, emails: Sequence[str]) -> list[ValidationResult]: ...
    def detect_provider(self, domain: str) -> str: ...             # yandex|mailru|google…
        # raises ValidationError только при системном сбое, невалидность → в result
```

### personalize
```python
class Personalizer:
    def __init__(self, config: Config, gen_provider: "GenProvider | None" = None): ...
    def render(self, step: SequenceStep, recipient: Recipient,
               campaign: Campaign) -> RenderedMessage: ...
        # raises PersonalizationGateError если остались незаполненные {pl=holders}
    def preview(self, step: SequenceStep, recipient: Recipient,
                campaign: Campaign) -> RenderedMessage: ...        # без гейта, для теста
    def available_fields(self, recipient: Recipient) -> dict[str, Any]: ...

class GenProvider(Protocol):                                       # AI-хук ОКВЭД→оборудование
    def suggest_equipment(self, okved: str, segment: str | None) -> str: ...
```

### sender
```python
class Sender:
    def __init__(self, config: Config, store: Store, suppression: Suppression,
                 gates: "Gates", dry_run: bool = False): ...
    def pick_mailbox(self, recipient: Recipient, campaign: Campaign) -> str | None: ...
        # провайдер-сплит + лимиты + окно + пауза; None если некому слать сейчас
    def can_send_now(self, mailbox_id: str, *, now: datetime) -> bool: ...
    def send(self, message: Message, rendered: RenderedMessage,
             mailbox_id: str) -> SendResult: ...
        # ставит List-Unsubscribe/List-Unsubscribe-Post; в dry_run → в песочницу
        # raises RateLimitExceeded | GateTrippedError | SendError | TransientError
    def build_headers(self, message: Message, campaign: Campaign,
                      mailbox_id: str) -> dict[str, str]: ...
```

### imap_watcher
```python
class ImapWatcher:
    def __init__(self, config: Config, store: Store, suppression: Suppression,
                 reply_desk: "ReplyDeskSink | None" = None): ...
    def poll_once(self, mailbox_id: str) -> list[InboundEvent]: ...
        # классифицирует reply|dsn|complaint, дедупает по (uidvalidity,uid),
        # стоп цепочки + suppress при bounce/complaint, тред-линк
    def run(self, *, interval_sec: int, stop: "threading.Event") -> None: ...
    def classify(self, raw: bytes) -> InboundEvent: ...

class ReplyDeskSink(Protocol):
    def push_warm_lead(self, recipient: Recipient, thread_id: str, snippet: str) -> None: ...
```

### cadence
```python
class Cadence:
    def __init__(self, config: Config, store: Store, suppression: Suppression): ...
    def plan_campaign(self, campaign_id: int, *, now: datetime) -> list[MessageIn]: ...
        # разворачивает шаги в очередь с учётом engagement-gate/праздников/окон
        # НЕ шлёт дубль ответившему; не планирует suppressed
    def next_step_for(self, recipient_id: int, campaign_id: int) -> SequenceStep | None: ...
    def evaluate_gate(self, step: SequenceStep, recipient: Recipient,
                      campaign_id: int) -> CadenceDecision: ...   # send|skip|stop
    def schedule_time(self, base: datetime, step: SequenceStep) -> datetime: ...
        # рандом-интервал + перенос за окно/праздник
```

### gates
```python
class Gates:
    def __init__(self, config: Config, store: Store): ...
    def check_domain(self, domain: str, campaign_id: int | None = None) -> GateDecision: ...
    def check_mailbox(self, mailbox_id: str) -> GateDecision: ...
    def check_global(self) -> GateDecision: ...
    def evaluate_all(self) -> list[GateDecision]: ...    # для orchestrator, ставит паузы
    def trip(self, scope: str, target: str, reason: str) -> None: ...  # ручной kill-switch
```

### unsub
```python
class Unsub:
    """One-click RFC 8058. HTTP-эндпоинт отдаётся веб-слоем, здесь логика токена."""
    def __init__(self, config: Config, store: Store, suppression: Suppression): ...
    def make_token(self, recipient_id: int, campaign_id: int) -> str: ...   # подписанный
    def list_unsubscribe_headers(self, token: str) -> dict[str, str]: ...
        # {'List-Unsubscribe': '<https://…>, <mailto:…>',
        #  'List-Unsubscribe-Post': 'List-Unsubscribe=One-Click'}
    def handle_one_click(self, token: str) -> UnsubResult: ...
        # верифицирует токен → suppression.add_email(reason='unsubscribe'); идемпотентно
        # raises ValidationError при плохой подписи
```

### analytics
```python
class Analytics:
    def __init__(self, store: Store): ...
    def campaign_report(self, campaign_id: int) -> CampaignReport: ...
    def mailbox_report(self, mailbox_id: str, *, since: datetime | None = None) -> MailboxReport: ...
    def warmup_report(self, mailbox_id: str) -> WarmupReport: ...
    def global_report(self, *, since: datetime | None = None) -> GlobalReport: ...
    def rates(self, *, scope: str, target: str) -> RateSnapshot: ...  # bounce%/complaint%/reply%
```

### warmup
```python
class Warmup:
    def __init__(self, config: Config, store: Store, sender: Sender): ...
    def daily_target(self, mailbox_id: str, *, now: datetime) -> int: ...   # из рамп-кривой
    def run_cycle(self, mailbox_id: str, *, now: datetime) -> WarmupCycleResult: ...
        # живой микро-прогрев ящик↔ящик (свой пул), учёт reputation_score
    def reputation(self, mailbox_id: str) -> float: ...
```

### orchestrator
```python
class Orchestrator:
    def __init__(self, config: Config, store: Store, sender: Sender,
                 cadence: Cadence, gates: Gates, imap: ImapWatcher,
                 warmup: Warmup, analytics: Analytics): ...
    def bootstrap(self) -> None: ...            # init_schema + recover_stale
    def tick(self, *, now: datetime) -> TickResult: ...
        # 1) recover_stale 2) imap.poll 3) gates.evaluate_all
        # 4) cadence.plan 5) claim+render+send 6) warmup 7) метрики
    def run(self, *, interval_sec: int, dry_run: bool = False,
            stop: "threading.Event") -> None: ...
    def pause_all(self, reason: str) -> None: ...
    def resume_all(self) -> None: ...
```

---

## 3. Форматы обмена

```python
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional

# ---- входные DTO (в store) ----
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
    legal_entity: str          # "ООО Руспром"
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
    engagement_gate: str = "all"   # all|not_bounced|engaged
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
    scope: str        # email|domain|inn
    value: str
    reason: str
    source: str = ""
    campaign_id: Optional[int] = None
    expires_at: Optional[datetime] = None

# ---- сущности (из store) ----
@dataclass(frozen=True)
class Recipient:
    id: int; email: str; domain: str
    inn: Optional[str]; company_name: Optional[str]; okved: Optional[str]
    segment: Optional[str]; bitrix_id: Optional[str]; contact_name: Optional[str]
    mx_provider: Optional[str]; valid_status: str
    catch_all: Optional[bool]; role_based: Optional[bool]; disposable: Optional[bool]
    source: Optional[str]; extra: dict[str, Any]
    created_at: datetime; updated_at: datetime

@dataclass(frozen=True)
class Campaign:
    id: int; name: str; status: str
    legal_entity: str; legal_inn: str; provider_pool: Optional[str]
    config: dict[str, Any]
    created_at: datetime; started_at: Optional[datetime]

@dataclass(frozen=True)
class SequenceStep:
    id: int; campaign_id: int; step_index: int; delay_hours: int
    subject_tmpl: str; body_tmpl: str; engagement_gate: str
    include_legal: bool; active: bool

@dataclass(frozen=True)
class Message:
    id: int; idempotency_key: str
    campaign_id: int; recipient_id: int; sequence_step_id: int
    mailbox_id: Optional[str]; status: str
    scheduled_at: Optional[datetime]; claimed_at: Optional[datetime]; sent_at: Optional[datetime]
    rfc_message_id: Optional[str]; in_reply_to: Optional[str]; thread_id: Optional[str]
    subject: Optional[str]; body_rendered: Optional[str]
    unsub_token: Optional[str]; attempt_count: int; last_error: Optional[str]

@dataclass(frozen=True)
class SuppressionEntry:
    id: int; scope: str; value: str; reason: str
    source: Optional[str]; campaign_id: Optional[int]
    created_at: datetime; expires_at: Optional[datetime]

@dataclass
class MailboxState:
    mailbox_id: str; provider: str; day_key: str
    sent_today: int; sent_total: int; ramp_day: int; daily_limit: int
    last_sent_at: Optional[datetime]; paused: bool; pause_reason: Optional[str]

@dataclass
class WarmupState:
    mailbox_id: str; phase: str; ramp_day: int
    warmup_target: int; warmup_sent_today: int
    reputation_score: Optional[float]; day_key: str; last_warmup_at: Optional[datetime]

# ---- runtime-обмен между модулями ----
@dataclass(frozen=True)
class ValidationResult:
    email: str; valid_status: str            # valid|invalid|risky|unknown
    provider: str; mx_ok: bool
    catch_all: Optional[bool]; role_based: Optional[bool]; disposable: Optional[bool]
    detail: dict[str, Any] = field(default_factory=dict)

@dataclass(frozen=True)
class RenderedMessage:
    subject: str; body: str
    unfilled_fields: tuple[str, ...] = ()    # если непусто и не preview → gate падает
    used_ai: bool = False

@dataclass(frozen=True)
class SendResult:
    ok: bool; rfc_message_id: Optional[str]
    mailbox_id: str; sent_at: Optional[datetime]
    error: Optional[str] = None; retryable: bool = False
    dry_run: bool = False

@dataclass(frozen=True)
class InboundEvent:
    kind: str                                # reply|dsn|complaint|other
    mailbox_id: str; dedup_key: str
    rfc_message_id: Optional[str]            # исходное письмо (In-Reply-To/References)
    from_addr: str; thread_id: Optional[str]
    recipient_id: Optional[int]
    snippet: str; raw_headers: dict[str, str]

@dataclass(frozen=True)
class CadenceDecision:
    action: str                              # send|skip|stop
    reason: str

@dataclass(frozen=True)
class GateDecision:
    scope: str                               # domain|mailbox|global
    target: str; tripped: bool
    metric: str; value: float; threshold: float
    action: str                              # none|pause|resume

@dataclass(frozen=True)
class UnsubResult:
    ok: bool; recipient_id: Optional[int]; already: bool

@dataclass(frozen=True)
class RateSnapshot:
    scope: str; target: str
    sent: int; bounce: int; complaint: int; reply: int
    bounce_rate: float; complaint_rate: float; reply_rate: float

# отчёты analytics
@dataclass(frozen=True)
class CampaignReport:
    campaign_id: int; sent: int; delivered: int; bounced: int
    complaints: int; replies: int; unsubscribes: int
    bounce_rate: float; complaint_rate: float; reply_rate: float
    by_step: dict[int, RateSnapshot]

@dataclass(frozen=True)
class MailboxReport:
    mailbox_id: str; sent_today: int; sent_total: int
    ramp_day: int; daily_limit: int
    bounce_rate: float; complaint_rate: float; paused: bool

@dataclass(frozen=True)
class WarmupReport:
    mailbox_id: str; phase: str; ramp_day: int
    warmup_sent_today: int; reputation_score: Optional[float]

@dataclass(frozen=True)
class GlobalReport:
    total_sent: int; total_bounced: int; total_complaints: int
    global_bounce_rate: float; global_complaint_rate: float
    active_mailboxes: int; paused_mailboxes: int

@dataclass(frozen=True)
class TickResult:
    planned: int; sent: int; skipped: int; failed: int
    inbound: int; gates_tripped: int; warmup_sent: int

@dataclass(frozen=True)
class WarmupCycleResult:
    mailbox_id: str; sent: int; target: int; reputation_score: Optional[float]

# конфиг-структуры
@dataclass(frozen=True)
class MailboxCfg:
    mailbox_id: str; provider: str
    smtp_host: str; smtp_port: int; imap_host: str; imap_port: int
    login: str; password_env: str; from_name: str; signature: Optional[str]
    pool: Optional[str]; is_warmup_node: bool = False

@dataclass(frozen=True)
class WindowCfg:
    tz: str; days: tuple[int, ...]; start: str; end: str  # "09:00","18:30"

@dataclass(frozen=True)
class GatesCfg:
    domain_bounce_pct: float; domain_complaint_pct: float
    mailbox_bounce_pct: float; global_complaint_pct: float
    min_volume: int                         # порог статзначимости перед trip

@dataclass(frozen=True)
class LegalCfg:
    entity: str; inn: str; unsub_base_url: str
    unsub_secret_env: str; refusal_log_max_lag_hours: int
```

---

## 4. Конфиг (YAML)

```yaml
service:
  name: rusprom-sender
  db_path: /var/lib/rusprom/sender.db
  tick_interval_sec: 60
  dry_run: false
  sandbox_smtp: "localhost:8025"     # aiosmtpd для dry-run/тестов

timezone: "Europe/Moscow"

legal:                               # ФЗ-38 / ФЗ-152
  entity: "ООО «Руспром»"
  inn: "7700000000"
  unsub_base_url: "https://parsercompressor.online/u"
  unsub_secret_env: UNSUB_SIGNING_SECRET
  refusal_log_max_lag_hours: 24      # лог отказов ≤1 день

window:                              # окно отправки
  days: [1,2,3,4,5]                  # пн-пт (ISO)
  start: "09:30"
  end:   "18:00"

holidays:                            # переносим отправку
  - "2025-01-01"
  - "2025-01-07"
  - "2025-02-23"
  - "2025-03-08"
  - "2025-05-01"
  - "2025-05-09"
  - "2025-06-12"
  - "2025-11-04"

ramp_curves:                         # индекс = день рампа → лимит/день
  yandex:  [3, 5, 8, 12, 18, 25, 32, 40, 50]
  mailru:  [3, 5, 8, 12, 18, 25, 32, 40, 50]
  google:  [2, 3, 5, 8, 12, 18, 25, 35, 50]
  outlook: [2, 3, 5, 8, 12, 18, 25, 35, 50]

send_pacing:
  min_interval_sec: 90               # рандом между письмами с одного ящика
  max_interval_sec: 420
  jitter: true

provider_split:                      # роутинг по MX получателя
  match_recipient_provider: true     # yandex-домены → yandex-пул и т.д.
  pools:
    pool_yandex:  [box1@rusprom.ru, box2@rusprom.ru]
    pool_mailru:  [box3@rusprom.ru, box4@rusprom.ru]
    pool_google:  [box5@rusprom.ru]         # google-контур 2-3 ящика
    pool_fallback: [box1@rusprom.ru]
  routing:
    yandex:  pool_yandex
    mailru:  pool_mailru
    google:  pool_google
    other:   pool_fallback

mailboxes:
  - mailbox_id: box1@rusprom.ru
    provider: yandex
    smtp_host: smtp.yandex.ru
    smtp_port: 465
    imap_host: imap.yandex.ru
    imap_port: 993
    login: box1@rusprom.ru
    password_env: BOX1_PASSWORD
    from_name: "Иван Петров, Руспром"
    signature_ref: sig_ivan
    pool: pool_yandex
    is_warmup_node: false
  - mailbox_id: box5@rusprom.ru
    provider: google
    smtp_host: smtp.gmail.com
    smtp_port: 465
    imap_host: imap.gmail.com
    imap_port: 993
    login: box5@rusprom.ru
    password_env: BOX5_PASSWORD
    from_name: "Иван Петров, Руспром"
    signature_ref: sig_ivan
    pool: pool_google
    is_warmup_node: true             # только google-контур в прогрев-пуле

gates:                               # kill-switch пороги (%)
  domain_bounce_pct: 8.0
  domain_complaint_pct: 0.3
  mailbox_bounce_pct: 6.0
  global_complaint_pct: 0.1          # жёсткий глобальный стоп
  min_volume: 50                     # не триггерить на малой выборке

warmup:
  enabled_providers: [google]        # живой прогрев только там, где уместно
  ramp_curve: [2, 3, 5, 8, 12, 18, 25, 35, 50]
  reply_probability: 0.3             # доля «ответов» в живом прогреве
  reputation_floor: 0.6              # ниже → phase=paused

validation:
  check_mx: true
  detect_catch_all: true
  detect_role: true
  detect_disposable: true
  role_prefixes: [info, sales, office, admin, support, mail]

imap:
  poll_interval_sec: 120
  batch: 50
  auto_suppress_on_bounce: true
  auto_suppress_on_complaint: true

personalization:
  fail_on_unfilled: true             # гейт незаполненных {}
  ai_enabled: true                   # gen_provider: ОКВЭД→оборудование
  ai_fields: [equipment_pitch]

suppression:
  competitor_lists:
    - /etc/rusprom/competitors_domains.txt
  default_scope: domain

attribution:                         # для писем и отчётов
  entity: "ООО «Руспром»"
  entity_inn: "7700000000"
  include_inn_in_first_touch: true
```

---

## 5. Инварианты безопасности

Эти правила проверяются на уровне контракта и обязаны выполняться в любом порядке модулей и после любого рестарта.

1. Не слать дубль ответившему.
   - `cadence.plan_campaign` и `cadence.evaluate_gate` перед постановкой любого касания вызывают `store.has_reply(recipient_id, campaign_id)`; при `True` → `CadenceDecision(action='stop')`. Дополнительно `imap_watcher` при `kind='reply'` переводит все `pending/scheduled` сообщения этого `(recipient_id, campaign_id)` в `status='skipped'` (reason=`replied`). Гонку закрывает то, что `sender.send` вызывается только на строках, взятых через `store.claim_due_messages`, которая исключает получателей с событием `reply`.

2. Стоп-на-bounce.
   - Жёсткий bounce (5.x.x DSN) → `imap_watcher` пишет `event(bounce)` + `suppression.add_email(reason='bounce_hard')` и снимает будущие касания получателя (`skipped`). Планировщик с `engagement_gate='not_bounced'`/`'engaged'` не поставит следующий шаг. Мягкий bounce (4.x.x) не саппрессит, но инкрементит счётчик для гейтов.

3. Дедуп.
   - На уровне БД: `recipients.email UNIQUE`, `messages.idempotency_key UNIQUE`, `events.dedup_key UNIQUE`. Ни один модуль не полагается на «проверить-потом-вставить»: `enqueue_message`/`append_event` используют `ON CONFLICT DO NOTHING` и возвращают флаг «создано ли». Повторный поллинг IMAP того же UID не задваивает событие.

4. Гейт незаполненных `{}`.
   - `personalize.render` возвращает `RenderedMessage.unfilled_fields`; если непусто и не `preview`, бросает `PersonalizationGateError`. `sender.send` обязан отклонить сообщение с непустым `unfilled_fields` → `mark_failed(retryable=False)`. Ни одно письмо с сырым плейсхолдером не уходит.

5. Kill-switch по complaint-rate (и bounce).
   - Перед каждой волной `orchestrator.tick` вызывает `gates.evaluate_all`. При превышении `global_complaint_pct` (учёт только выборок ≥ `min_volume`) — `orchestrator.pause_all`; при доменном/ящичном превышении — `store.set_mailbox_paused`/пауза домена. `sender.can_send_now` и `store.claim_due_messages` не выдают сообщения для паузнутых ящиков/доменов. Снятие паузы — только явным `gates`/`resume_all`.

Дополнительные инварианты хребта:
- Идемпотентность отправки: `send` идёт только по строке в `status='sending'` с валидным lease; `mark_sent` записывает `rfc_message_id` (UNIQUE). Повторная попытка после сбоя до `mark_sent` безопасна — та же `idempotency_key`, `claim` не выдаст уже `sent`.
- Резюмируемость: `orchestrator.bootstrap` → `store.recover_stale(lease_ttl)` возвращает зависшие `sending` в `scheduled`. Счётчики `mailbox_state`/`warmup_state` персистентны и сбрасываются только по смене `day_key`.
- Юр-гейт ФЗ-38/152: `include_legal=1` у письма-1 обязателен; `sender.build_headers` всегда добавляет `List-Unsubscribe` + `List-Unsubscribe-Post: List-Unsubscribe=One-Click` (RFC 8058) из `unsub`. Отказ через `unsub.handle_one_click` попадает в `suppression` немедленно (лог ≤ `refusal_log_max_lag_hours`).
- Suppression-first: `store.claim_due_messages` фильтрует по `suppression_lookup` (email→domain→inn) в той же транзакции, что и lease — саппрессированный получатель не может быть отправлен, даже если сообщение уже стояло в очереди.
- Изоляция записи: только `store` пишет в БД; остальные модули читают через `store` и передают DTO — это и есть граница, позволяющая писать 12 модулей независимо.