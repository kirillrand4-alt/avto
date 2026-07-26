# -*- coding: utf-8 -*-
"""Общие DTO сендера (единый источник типов). Извлечено из раздела 3 контракта."""
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
    # Баллы приоритета из базы обзвона (P1.6)
    priority_max: Optional[int] = None
    priority_total: Optional[float] = None
    pxr: Optional[float] = None
    # Регион/таймзона получателя (P1.5: окно 9:00 по местному, пейсинг по региону)
    region: Optional[str] = None
    tz: Optional[str] = None
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
    # Баллы приоритета из базы обзвона (P1.6)
    priority_max: Optional[int] = None
    priority_total: Optional[float] = None
    pxr: Optional[float] = None
    # Регион/таймзона получателя (P1.5)
    region: Optional[str] = None
    tz: Optional[str] = None

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
    queued: int = 0   # в очередь подтверждений (confirm-режим оркестратора)

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
    provider_bounce_pct: float = 2.5        # bounce × провайдер получателя (mx_provider)
    # Ревью (подтверждено): без окна метрики считались за ВСЮ историю БД —
    # исторический «чистый» объём разбавлял знаменатель, и свежий всплеск
    # баунсов не пробивал порог (домен можно было сжечь). 0 = без окна.
    window_days: int = 14

@dataclass(frozen=True)
class LegalCfg:
    entity: str; inn: str; unsub_base_url: str
    unsub_secret_env: str; refusal_log_max_lag_hours: int
