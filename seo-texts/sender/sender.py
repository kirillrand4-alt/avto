# FILE: sender/sender.py
"""Модуль отправки холодной рассылки «Руспром».

Реализует публичный API `Sender` из контракта: провайдер-сплит выбор ящика,
дневные лимиты по рамп-кривой, окно отправки/праздники, пейсинг, SMTP-доставку
через smtplib (с dry-run в локальную песочницу, совместимую с aiosmtpd),
формирование заголовков с List-Unsubscribe + RFC 8058 и идемпотентную отправку.

Модуль зависит только от stdlib. Зависимости (Config/Store/Suppression/Gates)
описаны Protocol-интерфейсами — их конкретные реализации живут в своих модулях.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import os
import random
import smtplib
import socket
from contextlib import suppress
from dataclasses import dataclass, field
from datetime import date, datetime, time, timezone
from email.message import EmailMessage
from email.utils import format_datetime, formataddr, make_msgid
from typing import Any, Optional, Protocol, Sequence, runtime_checkable
from sender.errors import ConfigError, GateTrippedError, PersonalizationGateError, RateLimitExceeded, SendError, SenderError, StoreError, SuppressedError, TransientError, ValidationError  # noqa: E402

logger = logging.getLogger("sender.sender")

try:  # zoneinfo есть в 3.9+, оставляем безопасный фолбэк
    from zoneinfo import ZoneInfo
except Exception:  # pragma: no cover
    ZoneInfo = None  # type: ignore[assignment]

__all__ = [
    "SenderError", "ConfigError", "StoreError", "SuppressedError",
    "ValidationError", "PersonalizationGateError", "SendError",
    "RateLimitExceeded", "GateTrippedError", "TransientError",
    "MailboxCfg", "WindowCfg", "GatesCfg", "LegalCfg",
    "Recipient", "Campaign", "Message", "MailboxState", "SuppressionEntry",
    "RenderedMessage", "SendResult", "GateDecision", "EventIn",
    "Sender",
]


# --------------------------------------------------------------------------- #
# Иерархия исключений (общий хребет §2): общие классы из sender.errors, чтобы
# orchestrator ловил их по идентичности; фолбэк держит модуль автономным.
# --------------------------------------------------------------------------- #


# --------------------------------------------------------------------------- #
# DTO из §3, используемые сендером
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class Readiness:
    """Композитный флаг «ящик готов к бою» (Фаза 2.1, экран ящиков/конструктор)."""
    mailbox_id: str
    ready: bool
    ramp_day: int
    daily_limit: int
    sent_today: int
    paused: bool
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class MailboxCfg:
    mailbox_id: str
    provider: str
    smtp_host: str
    smtp_port: int
    imap_host: str
    imap_port: int
    login: str
    password_env: str
    from_name: str
    signature: Optional[str] = None
    pool: Optional[str] = None
    is_warmup_node: bool = False


@dataclass(frozen=True)
class WindowCfg:
    tz: str
    days: tuple[int, ...]
    start: str
    end: str


@dataclass(frozen=True)
class GatesCfg:
    domain_bounce_pct: float
    domain_complaint_pct: float
    mailbox_bounce_pct: float
    global_complaint_pct: float
    min_volume: int


@dataclass(frozen=True)
class LegalCfg:
    entity: str
    inn: str
    unsub_base_url: str
    unsub_secret_env: str
    refusal_log_max_lag_hours: int


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


@dataclass(frozen=True)
class RenderedMessage:
    subject: str
    body: str
    unfilled_fields: tuple[str, ...] = ()
    used_ai: bool = False


@dataclass(frozen=True)
class SendResult:
    ok: bool
    rfc_message_id: Optional[str]
    mailbox_id: str
    sent_at: Optional[datetime]
    error: Optional[str] = None
    retryable: bool = False
    dry_run: bool = False


@dataclass(frozen=True)
class GateDecision:
    scope: str
    target: str
    tripped: bool
    metric: str
    value: float
    threshold: float
    action: str


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


# --------------------------------------------------------------------------- #
# Protocol-интерфейсы зависимостей (duck typing, конкретика в своих модулях)
# --------------------------------------------------------------------------- #
@runtime_checkable
class ConfigLike(Protocol):
    def mailboxes(self) -> list[MailboxCfg]: ...
    def provider_pools(self) -> dict[str, list[str]]: ...
    def ramp_curve(self, provider: str) -> list[int]: ...
    def sending_window(self) -> WindowCfg: ...
    def holidays(self) -> set[date]: ...
    def gates(self) -> GatesCfg: ...
    def legal(self) -> LegalCfg: ...
    def get(self, dotted_key: str, default: Any = ...) -> Any: ...


@runtime_checkable
class StoreLike(Protocol):
    def get_recipient(self, recipient_id: int) -> Optional[Recipient]: ...
    def get_campaign(self, campaign_id: int) -> Optional[Campaign]: ...
    def get_message(self, message_id: int) -> Optional[Message]: ...
    def mark_sent(self, message_id: int, rfc_message_id: str, sent_at: datetime) -> None: ...
    def mark_failed(self, message_id: int, error: str, *, retryable: bool) -> None: ...
    def mark_skipped(self, message_id: int, reason: str) -> None: ...
    def increment_sent(self, mailbox_id: str, *, now: datetime) -> MailboxState: ...
    def append_event(self, e: EventIn) -> tuple[int, bool]: ...
    def get_mailbox_state(self, mailbox_id: str) -> Optional[MailboxState]: ...


@runtime_checkable
class SuppressionLike(Protocol):
    def is_suppressed(self, recipient: Recipient) -> Optional[SuppressionEntry]: ...


@runtime_checkable
class GatesLike(Protocol):
    def check_domain(self, domain: str, campaign_id: Optional[int] = None) -> GateDecision: ...
    def check_mailbox(self, mailbox_id: str) -> GateDecision: ...
    def check_global(self) -> GateDecision: ...


# --------------------------------------------------------------------------- #
# Вспомогательные функции
# --------------------------------------------------------------------------- #
def _parse_hhmm(value: str) -> time:
    hh, _, mm = value.partition(":")
    return time(hour=int(hh), minute=int(mm or 0))


def _as_utc(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _strip_crlf(value: Optional[str]) -> str:
    """П2: значение заголовка в одну строку (CR/LF → пробел).

    Merge-поля приходят из CSV/extra/AI; \\r\\n в теме — это либо инъекция
    заголовков, либо «ядовитое» письмо: EmailMessage бросает ValueError,
    сообщение зависает в 'sending' и травит каждый тик. Санируем на границе.
    """
    if not value:
        return ""
    return " ".join(value.splitlines())


# --------------------------------------------------------------------------- #
# Sender
# --------------------------------------------------------------------------- #
class Sender:
    """Отправитель: выбор ящика, гейты лимитов/окна и SMTP-доставка.

    Инварианты §5, за которые отвечает сендер:
      * гейт незаполненных {} (п.4): непустой ``unfilled_fields`` → mark_failed
        (retryable=False) + PersonalizationGateError, ни одно письмо с сырым
        плейсхолдером не уходит;
      * suppression-first: перед отправкой повторно проверяется suppression;
      * kill-switch (п.5): при tripped-гейте отправка отклоняется;
      * идемпотентность: уже ``sent`` сообщение не переотправляется;
      * юр-гейт ФЗ-38/152: build_headers всегда добавляет List-Unsubscribe и
        List-Unsubscribe-Post: List-Unsubscribe=One-Click (RFC 8058).
    """

    def __init__(self, config: ConfigLike, store: StoreLike,
                 suppression: SuppressionLike, gates: GatesLike,
                 dry_run: bool = False) -> None:
        self.config = config
        self.store = store
        self.suppression = suppression
        self.gates = gates
        self.dry_run = dry_run
        self._timeout = int(config.get("service.smtp_timeout_sec", 30) or 30)
        # Фабрика SMTP-соединений — переопределяема в тестах.
        self._smtp_opener = self._default_smtp_opener
        # open-tracking: трекер строится лениво и только при tracking.open_enabled
        self._open_tracker = None

    # ---- публичный API --------------------------------------------------- #
    def pick_mailbox(self, recipient: Recipient, campaign: Campaign,
                     *, now: Optional[datetime] = None,
                     manual: bool = False) -> Optional[str]:
        """Провайдер-сплит + лимиты + окно + пауза.

        Возвращает id наименее загруженного пригодного ящика из целевого пула,
        либо None, если слать сейчас некому. ``now`` инжектируется оркестратором
        (часы тика едины по всему пайплайну); без него — реальные часы.
        manual=True — ручная отправка: окно/пейсинг не учитываются при выборе.
        """
        now = _as_utc(now) if now is not None else datetime.now(timezone.utc)
        pool_name = self._route_pool(recipient, campaign)
        if not pool_name:
            return None
        mailbox_ids = self.config.provider_pools().get(pool_name, [])
        eligible: list[tuple[int, str]] = []
        for mid in mailbox_ids:
            if not self.can_send_now(mid, now=now, manual=manual):
                continue
            state = self.store.get_mailbox_state(mid)
            if state is None or state.day_key != self._day_key(now):
                load = 0
            else:
                load = state.sent_today
            eligible.append((load, mid))
        if not eligible:
            return None
        eligible.sort(key=lambda t: (t[0], t[1]))  # наименее загруженный, стабильно
        return eligible[0][1]

    def can_send_now(self, mailbox_id: str, *, now: datetime,
                     manual: bool = False) -> bool:
        """Можно ли слать с ящика прямо сейчас (гейты, пауза, лимит, окно, пейсинг).

        manual=True — РУЧНАЯ отправка оператором (нажал «Отправить»): окно
        отправки и межписьменный пейсинг ПРОПУСКАЮТСЯ (оператор осознанно шлёт
        одно письмо сейчас), но kill-switch/пауза/лимит дня ОСТАЮТСЯ — они про
        репутацию/безопасность, их обходить нельзя даже вручную.
        """
        now = _as_utc(now)
        mb = self._mailbox_cfg(mailbox_id)
        if mb is None:
            return False
        if self.gates.check_global().tripped:
            return False
        if self.gates.check_mailbox(mailbox_id).tripped:
            return False

        state = self.store.get_mailbox_state(mailbox_id)
        if state is not None and state.paused:
            return False

        if not manual and not self._within_window(now):
            return False

        today = self._day_key(now)
        if state is None:
            ramp_day, sent_today, last_sent_at = 0, 0, None
        elif state.day_key != today:
            # смена дня: счётчик обнулён, рамп-день инкрементируется
            ramp_day, sent_today, last_sent_at = state.ramp_day + 1, 0, None
        else:
            ramp_day = state.ramp_day
            sent_today = state.sent_today
            last_sent_at = _as_utc(state.last_sent_at)

        limit = self._daily_limit(mb.provider, ramp_day)
        if sent_today >= limit:
            return False

        if not manual and last_sent_at is not None:
            # НЕ «or 90»: явный 0 в конфиге легален (пейсинг выключен)
            raw_gap = self.config.get("send_pacing.min_interval_sec", 90)
            min_gap = 90 if raw_gap is None else int(raw_gap)
            if (now - last_sent_at).total_seconds() < min_gap:
                return False
        return True

    def build_headers(self, message: Message, campaign: Optional[Campaign],
                      mailbox_id: str) -> dict[str, str]:
        """Формирует заголовки письма, включая List-Unsubscribe (RFC 8058)."""
        mb = self._mailbox_cfg(mailbox_id)
        if mb is None:
            raise ConfigError(f"unknown mailbox {mailbox_id!r}")
        recipient = self.store.get_recipient(message.recipient_id)
        if recipient is None:
            raise ValidationError(f"recipient {message.recipient_id} not found")

        rfc_id = message.rfc_message_id or self._gen_message_id(mailbox_id)
        # П2: CR/LF в значениях из данных (тема из merge-полей, from_name,
        # email старых строк БД) санируются — см. _strip_crlf.
        headers: dict[str, str] = {
            "Message-ID": rfc_id,
            "Date": format_datetime(datetime.now(timezone.utc)),
            "From": formataddr((_strip_crlf(mb.from_name), mb.mailbox_id)),
            "To": _strip_crlf(recipient.email),
            "Subject": _strip_crlf(message.subject),
            "MIME-Version": "1.0",
        }
        if message.in_reply_to:
            headers["In-Reply-To"] = message.in_reply_to
            headers["References"] = message.in_reply_to

        # Юр-гейт: List-Unsubscribe присутствует всегда.
        token = message.unsub_token or self._make_unsub_token(
            message.recipient_id, message.campaign_id)
        headers.update(self._list_unsubscribe_headers(token, mb))
        return headers

    def send(self, message: Message, rendered: RenderedMessage,
             mailbox_id: str, *, now: Optional[datetime] = None,
             manual: bool = False) -> SendResult:
        """Отправляет одно письмо; в dry_run — в локальную песочницу.

        ``now`` — инжектируемые часы тика (лимит/окно/sent_at); без него —
        реальные. manual=True — РУЧНАЯ отправка оператором (нажал «Отправить»):
        окно/пейсинг пропускаются, но suppression/has_reply/kill-switch/пауза/
        лимит дня остаются (см. can_send_now). raises: RateLimitExceeded |
        GateTrippedError | SendError | TransientError | PersonalizationGateError
        | SuppressedError
        """
        injected_now = _as_utc(now) if now is not None else None
        # (1) Гейт незаполненных {} — до любых сетевых действий.
        if rendered.unfilled_fields:
            reason = "unfilled_placeholders:" + ",".join(rendered.unfilled_fields)
            self.store.mark_failed(message.id, reason, retryable=False)
            raise PersonalizationGateError(reason)

        # (2) Идемпотентность: уже отправленное не переотправляем.
        current = self.store.get_message(message.id) or message
        if current.status == "sent":
            return SendResult(
                ok=True, rfc_message_id=current.rfc_message_id,
                mailbox_id=mailbox_id, sent_at=_as_utc(current.sent_at),
                dry_run=self.dry_run)

        # (3) Suppression-first.
        recipient = self.store.get_recipient(message.recipient_id)
        if recipient is None:
            self.store.mark_failed(message.id, "recipient_not_found", retryable=False)
            raise SendError(f"recipient {message.recipient_id} not found")
        entry = self.suppression.is_suppressed(recipient)
        if entry is not None:
            self.store.mark_skipped(message.id, f"suppressed:{entry.reason}")
            raise SuppressedError(f"{recipient.email} suppressed ({entry.reason})")

        # (3b) П1.5: ответ мог прийти МЕЖДУ claim и send (claim фильтрует
        # reply-события, но окно между ними ненулевое) — followup после ответа
        # недопустим. Guard hasattr: у мок-store в юнитах метода может не быть.
        if hasattr(self.store, "has_reply") and self.store.has_reply(
                message.recipient_id, message.campaign_id):
            self.store.mark_skipped(message.id, "reply_received")
            raise SuppressedError(
                f"{recipient.email}: получен ответ, followup отменён")

        # (4) Kill-switch: глобальный → домен → ящик.
        if self.gates.check_global().tripped:
            raise GateTrippedError("global gate tripped")
        if self.gates.check_domain(recipient.domain, message.campaign_id).tripped:
            raise GateTrippedError(f"domain gate tripped: {recipient.domain}")
        if self.gates.check_mailbox(mailbox_id).tripped:
            raise GateTrippedError(f"mailbox gate tripped: {mailbox_id}")

        # (5) Лимит/окно/пейсинг. manual → окно/пейсинг обходятся (см. метод),
        # но лимит дня/пауза/kill-switch остаются.
        now = injected_now if injected_now is not None else datetime.now(timezone.utc)
        if not self.can_send_now(mailbox_id, now=now, manual=manual):
            raise RateLimitExceeded(f"{mailbox_id}: cannot send now")

        # (5b) Пер-регион пейсинг (P1.5): «каждые N сек для компаний ЭТОГО
        # региона» — интервал считается по последнему sent-событию региона,
        # независимо от ящика. 0/не задан = выключено (как раньше).
        # manual пропускает и его: оператор шлёт одно письмо осознанно.
        region_gap = int(self.config.get("send_pacing.per_region_interval_sec", 0) or 0)
        if not manual and region_gap > 0:
            region = getattr(recipient, "region", None)
            if region and hasattr(self.store, "last_sent_ts_for_region"):
                last_regional = self.store.last_sent_ts_for_region(region)
                if last_regional is not None:
                    last_regional = _as_utc(last_regional)
                    if (now - last_regional).total_seconds() < region_gap:
                        raise RateLimitExceeded(
                            f"region pacing {region}: жду {region_gap}с между письмами")

        # (6) Сборка письма.
        campaign = self.store.get_campaign(message.campaign_id)
        headers = self.build_headers(message, campaign, mailbox_id)
        if rendered.subject:
            headers["Subject"] = _strip_crlf(rendered.subject)
        rfc_id = headers["Message-ID"]
        mime_bytes = self._build_mime(
            headers, rendered, pixel_url=self._open_pixel_url(message, campaign))
        mb = self._mailbox_cfg(mailbox_id)
        assert mb is not None  # проверено в build_headers/can_send_now

        # (6b) TOCTOU-зазор (ревью, подтверждено): между шагом (3) и доставкой
        # проходят обращения к store (кампания/заголовки/лимиты) — IMAP-ридер
        # успевает добавить bounce/unsub в suppression. Последняя проверка
        # ПРЯМО перед сетью, когда всё уже собрано.
        entry = self.suppression.is_suppressed(recipient)
        if entry is not None:
            self.store.mark_skipped(message.id, f"suppressed:{entry.reason}")
            raise SuppressedError(
                f"{recipient.email} suppressed late ({entry.reason})")

        # (7) Доставка + классификация ошибок.
        try:
            self._deliver(mb, mb.mailbox_id, recipient.email, mime_bytes)
        except TransientError as e:
            self.store.mark_failed(message.id, str(e), retryable=True)
            raise
        except SendError as e:
            self.store.mark_failed(message.id, str(e), retryable=False)
            raise

        # (8) Фиксация успеха.
        sent_at = injected_now if injected_now is not None else datetime.now(timezone.utc)
        self.store.mark_sent(message.id, rfc_id, sent_at)
        # Задача 3 (confirm-send): send_log — история контактов и 90-дневный
        # заслон повторного касания. Guard hasattr: мок-store юнитов.
        if hasattr(self.store, "send_log_add"):
            try:
                self.store.send_log_add(
                    email=recipient.email, inn=recipient.inn,
                    campaign_id=message.campaign_id, ts=sent_at,
                    message_id=message.id, rfc_message_id=rfc_id,
                    subject=headers.get("Subject", ""), outcome="sent")
            except Exception:  # noqa: BLE001 - лог не роняет отправку
                logger.exception("send_log_add failed message_id=%s", message.id)
        # ФЗ-152: фиксируем правовое основание касания (guard: у мок-store в
        # юнитах метода может не быть — журнал не должен ронять отправку)
        if hasattr(self.store, "log_consent"):
            try:
                self.store.log_consent(
                    email=recipient.email,
                    action="send",
                    recipient_id=recipient.id,
                    basis="direct_b2b_offer",
                    source=f"send:{message.id}",
                    campaign_id=message.campaign_id,
                )
            except Exception:  # noqa: BLE001
                logger.exception("log_consent failed message_id=%s", message.id)
        # П2.7: день считаем в зоне конфига (та же, что у окна отправки), а не
        # по UTC — иначе счётчик/рамп катились бы в 03:00 МСК. Guard hasattr
        # для мок-store юнитов со старой сигнатурой.
        try:
            self.store.increment_sent(
                mailbox_id, now=sent_at, day_key=self._day_key(sent_at))
        except TypeError:
            self.store.increment_sent(mailbox_id, now=sent_at)
        self.store.append_event(EventIn(
            dedup_key=f"send:{message.id}", event_type="sent", event_ts=sent_at,
            message_id=message.id, recipient_id=message.recipient_id,
            campaign_id=message.campaign_id, mailbox_id=mailbox_id,
            provider=mb.provider))
        return SendResult(ok=True, rfc_message_id=rfc_id, mailbox_id=mailbox_id,
                          sent_at=sent_at, dry_run=self.dry_run)

    def send_reply(self, *, to_email: str, subject: str, body: str,
                   mailbox_id: str, in_reply_to: Optional[str] = None,
                   thread_id: Optional[str] = None,
                   recipient_id: Optional[int] = None) -> SendResult:
        """Отправить РУЧНОЙ ответ в тред (реакция на входящее письмо клиента).

        Это диалог, а не рассылка: окно/пейсинг/каденция не применяются, но
        юр-заслон отписки/жалобы ОСТАЁТСЯ (отписавшемуся не пишем даже в ответ),
        как и kill-switch ящика. In-Reply-To/References держат письмо в треде.
        List-Unsubscribe в ответе не ставим (это не рекламная рассылка).
        Атрибуция «ООО «Руспром»» уже в теле (render_reply/qa_reply следят).
        """
        to_email = (to_email or "").strip().lower()
        if not to_email:
            raise ValidationError("send_reply: пустой адрес")

        # Юр-заслон: отписка/жалоба сильнее ответа.
        from types import SimpleNamespace
        domain = to_email.rsplit("@", 1)[-1] if "@" in to_email else ""
        inn = None
        if recipient_id is not None:
            rcp = self.store.get_recipient(recipient_id)
            if rcp is not None:
                inn = rcp.inn
        entry = self.suppression.is_suppressed(
            SimpleNamespace(email=to_email, domain=domain, inn=inn))
        if entry is not None and entry.reason in ("unsubscribe", "complaint"):
            raise SuppressedError(
                f"{to_email} отписан/пожаловался ({entry.reason}) — не отвечаем")

        # kill-switch ящика (горящий ящик не используем даже для ответа).
        if self.gates.check_global().tripped:
            raise GateTrippedError("global gate tripped")
        if self.gates.check_mailbox(mailbox_id).tripped:
            raise GateTrippedError(f"mailbox gate tripped: {mailbox_id}")

        mb = self._mailbox_cfg(mailbox_id)
        if mb is None:
            raise ConfigError(f"unknown mailbox {mailbox_id!r}")

        rfc_id = self._gen_message_id(mailbox_id)
        headers: dict[str, str] = {
            "Message-ID": rfc_id,
            "Date": format_datetime(datetime.now(timezone.utc)),
            "From": formataddr((_strip_crlf(mb.from_name), mb.mailbox_id)),
            "To": _strip_crlf(to_email),
            "Subject": _strip_crlf(subject),
            "MIME-Version": "1.0",
        }
        if in_reply_to:
            headers["In-Reply-To"] = _strip_crlf(in_reply_to)
            headers["References"] = _strip_crlf(in_reply_to)

        mime_bytes = self._build_mime(headers, RenderedMessage(subject=subject, body=body))
        self._deliver(mb, mb.mailbox_id, to_email, mime_bytes)

        sent_at = datetime.now(timezone.utc)
        if hasattr(self.store, "send_log_add"):
            try:
                self.store.send_log_add(
                    email=to_email, inn=inn, ts=sent_at, rfc_message_id=rfc_id,
                    subject=subject, outcome="reply_sent")
            except Exception:  # noqa: BLE001
                logger.exception("send_log_add failed (reply) to=%s", to_email)
        with suppress(Exception):
            self.store.increment_sent(mailbox_id, now=sent_at,
                                      day_key=self._day_key(sent_at))
        with suppress(Exception):
            self.store.append_event(EventIn(
                dedup_key=f"reply_sent:{thread_id or to_email}:{rfc_id}",
                event_type="reply_sent", event_ts=sent_at,
                recipient_id=recipient_id, mailbox_id=mailbox_id,
                provider=mb.provider))
        return SendResult(ok=True, rfc_message_id=rfc_id, mailbox_id=mailbox_id,
                          sent_at=sent_at, dry_run=self.dry_run)

    def pacing_interval(self) -> int:
        """Случайный интервал (сек) между письмами одного ящика для планировщика."""
        lo = int(self.config.get("send_pacing.min_interval_sec", 90) or 90)
        hi = int(self.config.get("send_pacing.max_interval_sec", 420) or 420)
        if self.config.get("send_pacing.jitter", True) and hi > lo:
            return random.randint(lo, hi)
        return lo

    # ---- приватные помощники -------------------------------------------- #
    def _route_pool(self, recipient: Recipient, campaign: Campaign) -> Optional[str]:
        routing = self.config.get("provider_split.routing", {}) or {}
        if self.config.get("provider_split.match_recipient_provider", True):
            provider = (recipient.mx_provider or "unknown").lower()
            pool = routing.get(provider) or routing.get("other")
            if pool:
                return pool
        if campaign is not None and campaign.provider_pool:
            return campaign.provider_pool
        return routing.get("other")

    def _mailbox_cfg(self, mailbox_id: str) -> Optional[MailboxCfg]:
        for mb in self.config.mailboxes():
            if mb.mailbox_id == mailbox_id:
                return mb
        return None

    def mailbox_readiness(self, mailbox_id: str, *, now: Optional[datetime] = None) -> Readiness:
        """Композитный флаг готовности ящика (локальные сигналы, без сети).

        NEW-BACKEND для веб-панели: флаг «Готов к бою» на экране ящиков и
        дропдаун-гейт в конструкторе. DNS/Постофис подключаются отдельно
        (sender/dns.py, postoffice.py) — здесь только паузa/гейт/квота/окно.
        """
        now = _as_utc(now) if now is not None else datetime.now(timezone.utc)
        state = self.store.get_mailbox_state(mailbox_id)
        if state is None:
            return Readiness(mailbox_id=mailbox_id, ready=False, ramp_day=0,
                             daily_limit=0, sent_today=0, paused=False,
                             reasons=("no_state",))
        reasons: list[str] = []
        if state.paused:
            reasons.append("paused")
        try:
            if self.gates.check_mailbox(mailbox_id).tripped:
                reasons.append("gate_tripped")
        except Exception:  # noqa: BLE001
            pass
        if state.sent_today >= state.daily_limit:
            reasons.append("quota_exhausted")
        if not self._within_window(now):
            reasons.append("outside_window")
        return Readiness(
            mailbox_id=mailbox_id, ready=not reasons, ramp_day=int(state.ramp_day),
            daily_limit=int(state.daily_limit), sent_today=int(state.sent_today),
            paused=bool(state.paused), reasons=tuple(reasons),
        )

    def _daily_limit(self, provider: str, ramp_day: int) -> int:
        # P2 №1: единый резолвер рамп-кривой (общий с orchestrator-сидом)
        from sender.ramp import daily_send_limit
        return daily_send_limit(self.config, provider, ramp_day)

    def _within_window(self, now: datetime) -> bool:
        win = self.config.sending_window()
        local = now.astimezone(self._zone(win.tz))
        if local.isoweekday() not in win.days:
            return False
        if local.date() in self.config.holidays():
            return False
        start = _parse_hhmm(win.start)
        end = _parse_hhmm(win.end)
        return start <= local.time() <= end

    def _day_key(self, now: datetime) -> str:
        tz_name = self.config.get("timezone", "UTC")
        return now.astimezone(self._zone(tz_name)).strftime("%Y-%m-%d")

    @staticmethod
    def _zone(name: str):
        if ZoneInfo is None or not name:
            return timezone.utc
        try:
            return ZoneInfo(name)
        except Exception:
            return timezone.utc

    def _gen_message_id(self, mailbox_id: str) -> str:
        domain = mailbox_id.split("@")[-1] if "@" in mailbox_id else "localhost"
        return make_msgid(domain=domain)

    def _make_unsub_token(self, recipient_id: int, campaign_id: int) -> str:
        """Подписанный токен one-click отписки.

        FIX (сверх ревью-списка, юр-критично): раньше здесь был СВОЙ формат
        ``b64(rid:cid).sig``, а unsub_server проверяет формат sender.tokens
        (JSON {"rid","cid","ts"}) — ссылка из боевого письма давала 400 и
        отписка не работала вообще. Теперь токен выпускает то же ядро
        sender.tokens, которым его проверяет Unsub._verify_token.
        """
        legal = self.config.legal()
        secret = os.environ.get(legal.unsub_secret_env)
        if not secret:
            raise ConfigError(f"missing unsub secret env {legal.unsub_secret_env}")
        from sender.tokens import sign_token
        payload = {
            "rid": int(recipient_id),
            "cid": int(campaign_id),
            "ts": int(datetime.now(timezone.utc).timestamp()),
        }
        return sign_token(secret.encode(), payload)

    def _list_unsubscribe_headers(self, token: str, mb: MailboxCfg) -> dict[str, str]:
        legal = self.config.legal()
        base = legal.unsub_base_url.rstrip("/")
        sep = "&" if "?" in base else "?"
        # Параметр строго `t` — его читает unsub_server._parse_token (раньше
        # писали `token=`, сервер отвечал «Missing token parameter»).
        url = f"{base}{sep}t={token}"
        mailto = f"mailto:{mb.mailbox_id}?subject=unsubscribe"
        return {
            "List-Unsubscribe": f"<{url}>, <{mailto}>",
            "List-Unsubscribe-Post": "List-Unsubscribe=One-Click",
        }

    def _open_pixel_url(self, message: Message, campaign: Optional[Campaign]) -> Optional[str]:
        """URL трекинг-пикселя или None (выключено/нет секрета/ошибка).

        Ошибка построения пикселя НИКОГДА не блокирует отправку — просто
        письмо уходит без трекинга (open — справочный сигнал).
        """
        if not bool(self.config.get("tracking.open_enabled", False)):
            return None
        try:
            from sender.tracking import OpenTracker
            if self._open_tracker is None:
                self._open_tracker = OpenTracker(self.config, self.store)
            tracker = self._open_tracker
            if not tracker.enabled_for(campaign):
                return None
            token = tracker.make_token(
                message.id, message.recipient_id, message.campaign_id)
            return tracker.pixel_url(token)
        except Exception:  # noqa: BLE001
            logger.exception("open-tracking: пиксель не построен, шлём без него")
            return None

    def _build_mime(self, headers: dict[str, str], rendered: RenderedMessage,
                    *, pixel_url: Optional[str] = None) -> bytes:
        msg = EmailMessage()
        msg.set_content(rendered.body or "")  # управляет Content-Type/CTE
        if pixel_url:
            # Пиксель живёт только в HTML-альтернативе; text/plain остаётся
            # каноничным телом (multipart/alternative, HTML — предпочтительный).
            from sender.tracking import inject_pixel, text_to_html
            msg.add_alternative(
                inject_pixel(text_to_html(rendered.body or ""), pixel_url),
                subtype="html")
        skip = {"Content-Type", "Content-Transfer-Encoding", "MIME-Version"}
        for key, value in headers.items():
            if key in skip or value is None:
                continue
            msg[key] = value
        return msg.as_bytes()

    def _sandbox_addr(self) -> tuple[str, int]:
        raw = self.config.get("service.sandbox_smtp", "localhost:8025") or "localhost:8025"
        host, _, port = raw.partition(":")
        return host or "localhost", int(port or 25)

    def _default_smtp_opener(self, host: str, port: int, use_ssl: bool):
        if use_ssl:
            return smtplib.SMTP_SSL(host, port, timeout=self._timeout)
        return smtplib.SMTP(host, port, timeout=self._timeout)

    def _deliver(self, mb: MailboxCfg, from_addr: str, to_addr: str,
                 mime_bytes: bytes) -> None:
        """Открывает соединение и шлёт письмо. Классифицирует SMTP-ошибки."""
        if self.dry_run:
            host, port = self._sandbox_addr()
            use_ssl = False
            password = None
        else:
            host, port = mb.smtp_host, mb.smtp_port
            use_ssl = (mb.smtp_port == 465)
            password = os.environ.get(mb.password_env)
            if not password:
                raise SendError(f"missing password env {mb.password_env}")

        try:
            client = self._smtp_opener(host, port, use_ssl)
        except (smtplib.SMTPConnectError, socket.error, ConnectionError,
                TimeoutError, OSError) as e:
            raise TransientError(f"connect failed: {e}") from e

        try:
            # П2: submission-порт (587 и любой не-SSL, кроме песочницы) обязан
            # подняться в TLS ДО login — иначе пароль ушёл бы открытым текстом.
            # Раньше starttls() не вызывался вовсе: провайдеры резали AUTH, а
            # на разрешающих серверах пароль улетал в plaintext.
            if not self.dry_run and not use_ssl:
                try:
                    client.starttls()
                    # RFC 3207: после STARTTLS сессия начинается заново
                    with suppress(Exception):
                        client.ehlo()
                except smtplib.SMTPException as e:
                    raise SendError(
                        f"STARTTLS недоступен на {host}:{port} — "
                        f"пароль открытым текстом не отправляем: {e}") from e
                except (socket.error, ConnectionError, TimeoutError, OSError) as e:
                    raise TransientError(f"starttls io: {e}") from e
            if not self.dry_run and password:
                try:
                    client.login(mb.login, password)
                except smtplib.SMTPAuthenticationError as e:
                    raise SendError(f"auth failed: {e}") from e
                except smtplib.SMTPException as e:
                    raise TransientError(f"login io: {e}") from e
            try:
                client.sendmail(from_addr, [to_addr], mime_bytes)
            except smtplib.SMTPRecipientsRefused as e:
                raise self._classify_recipients(e) from e
            except (smtplib.SMTPSenderRefused, smtplib.SMTPDataError,
                    smtplib.SMTPResponseException) as e:
                raise self._classify_code(getattr(e, "smtp_code", 554), str(e)) from e
            except (smtplib.SMTPServerDisconnected, socket.error, ConnectionError,
                    TimeoutError, OSError) as e:
                raise TransientError(f"smtp io: {e}") from e
        finally:
            with suppress(Exception):
                client.quit()

    @staticmethod
    def _classify_code(code: int, msg: str) -> SenderError:
        try:
            code = int(code)
        except (TypeError, ValueError):
            code = 554
        if 400 <= code < 500:
            return TransientError(msg)
        return SendError(msg)

    @staticmethod
    def _classify_recipients(e: smtplib.SMTPRecipientsRefused) -> SenderError:
        codes = [c for (c, _m) in e.recipients.values()]
        if codes and all(400 <= int(c) < 500 for c in codes):
            return TransientError(str(e))
        return SendError(str(e))
