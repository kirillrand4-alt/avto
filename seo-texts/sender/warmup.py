# FILE: sender/warmup.py
"""Свой живой микро-прогрев ящиков (не пул).

Модуль реализует публичный API `Warmup` из контракта: рамп-кривая объёма
(2-3 → 50 писем/день/ящик), персистентный `warmup_state`, интеграция с
`sender` для реальной отправки малыми дозами между собственными
прогрев-ящиками (ящик↔ящик, свой контур). Репутация — эвристика по
результатам отправок (delivered/bounce), с гейтом `reputation_floor`.

Зависимости: только stdlib. Тип-хинты на `Config`/`Store`/`Sender` — по
контракту §2/§3; здесь используются как duck-typed интерфейсы, чтобы
модуль оставался независимым.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional
from sender.errors import ConfigError, GateTrippedError, PersonalizationGateError, RateLimitExceeded, SendError, SenderError, StoreError, SuppressedError, TransientError, ValidationError  # noqa: E402

try:  # tz из конфига; фолбэк на UTC, если zoneinfo/база tz недоступны
    from zoneinfo import ZoneInfo
except Exception:  # pragma: no cover - экзотические окружения
    ZoneInfo = None  # type: ignore[assignment]


# --------------------------------------------------------------------------
# Иерархия исключений (по контракту §2)
# --------------------------------------------------------------------------


# --------------------------------------------------------------------------
# DTO (подмножество §3, необходимое модулю warmup)
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class EventIn:
    """Входной DTO события для append-only журнала."""

    dedup_key: str
    event_type: str
    event_ts: datetime
    message_id: Optional[int] = None
    recipient_id: Optional[int] = None
    campaign_id: Optional[int] = None
    mailbox_id: Optional[str] = None
    provider: Optional[str] = None
    detail: dict[str, Any] = field(default_factory=dict)


@dataclass
class MailboxState:
    """Дневные счётчики и статус ящика."""

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
    """Персистентное состояние живого прогрева ящика."""

    mailbox_id: str
    phase: str
    ramp_day: int
    warmup_target: int
    warmup_sent_today: int
    reputation_score: Optional[float]
    day_key: str
    last_warmup_at: Optional[datetime]


@dataclass(frozen=True)
class Message:
    """Синтетическое прогрев-сообщение для передачи в `sender.send`."""

    id: int
    idempotency_key: str
    campaign_id: int
    recipient_id: int
    sequence_step_id: int
    mailbox_id: Optional[str] = None
    status: str = "sending"
    scheduled_at: Optional[datetime] = None
    claimed_at: Optional[datetime] = None
    sent_at: Optional[datetime] = None
    rfc_message_id: Optional[str] = None
    in_reply_to: Optional[str] = None
    thread_id: Optional[str] = None
    subject: Optional[str] = None
    body_rendered: Optional[str] = None
    unsub_token: Optional[str] = None
    attempt_count: int = 0
    last_error: Optional[str] = None


@dataclass(frozen=True)
class RenderedMessage:
    """Готовый к отправке текст письма."""

    subject: str
    body: str
    unfilled_fields: tuple[str, ...] = ()
    used_ai: bool = False


@dataclass(frozen=True)
class SendResult:
    """Результат попытки отправки."""

    ok: bool
    rfc_message_id: Optional[str]
    mailbox_id: str
    sent_at: Optional[datetime]
    error: Optional[str] = None
    retryable: bool = False
    dry_run: bool = False


@dataclass(frozen=True)
class WarmupCycleResult:
    """Итог одного цикла прогрева."""

    mailbox_id: str
    sent: int
    target: int
    reputation_score: Optional[float]


# --------------------------------------------------------------------------
# Константы эвристики
# --------------------------------------------------------------------------
_DEFAULT_CURVE = (2, 3, 5, 8, 12, 18, 25, 35, 50)
_DEFAULT_FLOOR = 0.6
_DEFAULT_REPLY_PROB = 0.3
_DEFAULT_REPUTATION = 1.0

# Веса эвристики репутации (детерминированы, без сети).
_REP_FAIL_WEIGHT = 0.2      # каждый жёсткий провал/bounce
_REP_BASE_GAIN = 0.02       # базовый прирост за успешную доставку
_REP_REPLY_GAIN = 0.05      # прирост, масштабируемый ожидаемой долей ответов


def _resolve_tz(name: str):
    """Возвращает tzinfo по имени; фолбэк на UTC."""
    if ZoneInfo is not None:
        try:
            return ZoneInfo(name)
        except Exception:
            pass
    return timezone.utc


class Warmup:
    """Живой микро-прогрев собственного пула ящиков.

    Отправка идёт ящик↔ящик внутри провайдер-контура (например, google),
    объём ограничен рамп-кривой на день. Состояние персистентно в
    `warmup_state`, репутация обновляется по факту доставок/провалов и
    гейтится `reputation_floor` (ниже → phase=paused).
    """

    def __init__(self, config: Any, store: Any, sender: Any) -> None:
        self._config = config
        self._store = store
        self._sender = sender

        wu = config.get("warmup", {}) or {}
        self._enabled_providers = set(wu.get("enabled_providers", []) or [])
        curve = wu.get("ramp_curve") or list(_DEFAULT_CURVE)
        if not curve:
            raise ConfigError("warmup.ramp_curve пуст")
        self._curve = [int(x) for x in curve]
        self._reply_probability = float(wu.get("reply_probability", _DEFAULT_REPLY_PROB))
        self._reputation_floor = float(wu.get("reputation_floor", _DEFAULT_FLOOR))

        self._tz = _resolve_tz(config.get("timezone", "UTC") or "UTC")

        # Кэш конфигов ящиков по mailbox_id.
        self._mailbox_cfgs = {mb.mailbox_id: mb for mb in config.mailboxes()}

    # -- публичный API ----------------------------------------------------
    def daily_target(self, mailbox_id: str, *, now: datetime) -> int:
        """Целевой объём прогрева на сегодня из рамп-кривой.

        Возвращает 0 для ящиков вне прогрев-контура. Учитывает смену дня:
        при новом `day_key` рамп-день продвигается на 1 (пик — последний
        элемент кривой, дальше плато).
        """
        if not self._is_enabled(mailbox_id):
            return 0
        st = self._store.get_warmup_state(mailbox_id)
        today = self._day_key(now)
        ramp_day = self._effective_ramp_day(st, today)
        return self._curve_value(ramp_day)

    def reputation(self, mailbox_id: str) -> float:
        """Текущая репутация ящика в прогреве (0..1).

        Если состояния нет или счёт не заведён — оптимистичный дефолт 1.0.
        """
        st = self._store.get_warmup_state(mailbox_id)
        if st is None or st.reputation_score is None:
            return _DEFAULT_REPUTATION
        return float(st.reputation_score)

    def run_cycle(self, mailbox_id: str, *, now: datetime) -> WarmupCycleResult:
        """Один цикл живого прогрева ящика.

        Инварианты:
        - объём за день не превышает `daily_target` (идемпотентно по дню);
        - при репутации ниже `reputation_floor` — phase=paused, отправок нет;
        - смена дня сбрасывает `warmup_sent_today` и продвигает рамп-день;
        - каждая отправка проверяет `sender.can_send_now` (окно/пауза);
        - события пишутся идемпотентно (уникальный dedup_key).
        """
        cfg = self._mailbox_cfgs.get(mailbox_id)
        provider = cfg.provider if cfg is not None else None
        today = self._day_key(now)

        # Прогрев неприменим — не плодим состояние.
        if not self._is_enabled(mailbox_id):
            return WarmupCycleResult(mailbox_id, 0, 0, None)

        st = self._store.get_warmup_state(mailbox_id)
        rep = self.reputation(mailbox_id)
        ramp_day = self._effective_ramp_day(st, today)
        rolled_over = st is not None and st.day_key != today
        warmup_sent_today = 0 if (st is None or rolled_over) else st.warmup_sent_today
        last_warmup_at = None if st is None else st.last_warmup_at

        target = self._curve_value(ramp_day)

        # Гейт репутации: ниже пола — пауза, отправок нет.
        if rep < self._reputation_floor:
            self._persist(
                mailbox_id, "paused", ramp_day, target,
                warmup_sent_today, rep, today, last_warmup_at, now,
            )
            return WarmupCycleResult(mailbox_id, 0, target, rep)

        remaining = max(0, target - warmup_sent_today)
        peers = self._peers(mailbox_id, provider)

        sent = 0
        failures = 0
        if remaining > 0 and peers:
            start_count = warmup_sent_today
            for i in range(remaining):
                if not self._sender.can_send_now(mailbox_id, now=now):
                    break
                peer = peers[i % len(peers)]
                seq = start_count + sent
                message = self._build_message(mailbox_id, peer, now, seq, today)
                rendered = self._build_rendered(mailbox_id, peer)
                try:
                    res = self._sender.send(message, rendered, mailbox_id)
                except (RateLimitExceeded, GateTrippedError, TransientError):
                    # Стоп текущего цикла — повторим позже.
                    break
                except SendError as exc:
                    failures += 1
                    self._append_bounce(mailbox_id, provider, peer, now, today, seq, str(exc))
                    break
                if res is not None and res.ok:
                    self._store.append_event(EventIn(
                        dedup_key=f"warmup:sent:{mailbox_id}:{peer}:{today}:{seq}",
                        event_type="sent",
                        event_ts=now,
                        mailbox_id=mailbox_id,
                        provider=provider,
                        detail={"warmup": True, "peer": peer,
                                "rfc_message_id": res.rfc_message_id},
                    ))
                    sent += 1
                else:
                    failures += 1
                    err = res.error if res is not None else "send_failed"
                    retryable = bool(res.retryable) if res is not None else False
                    if not retryable:
                        self._append_bounce(mailbox_id, provider, peer, now, today, seq, err)
                    break

        warmup_sent_today += sent
        rep = self._update_reputation(rep, sent, failures)
        if sent > 0:
            last_warmup_at = now
        phase = self._phase(ramp_day, rep)

        self._persist(
            mailbox_id, phase, ramp_day, target,
            warmup_sent_today, rep, today, last_warmup_at, now,
        )
        return WarmupCycleResult(mailbox_id, sent, target, rep)

    # -- внутренняя логика ------------------------------------------------
    def _is_enabled(self, mailbox_id: str) -> bool:
        """Ящик участвует в прогреве: warmup-нода + провайдер в списке."""
        cfg = self._mailbox_cfgs.get(mailbox_id)
        if cfg is None:
            return False
        return bool(getattr(cfg, "is_warmup_node", False)) and cfg.provider in self._enabled_providers

    def _peers(self, mailbox_id: str, provider: Optional[str]) -> list[str]:
        """Прогрев-соседи того же провайдер-контура (без самого ящика)."""
        peers: list[str] = []
        for mb in self._config.mailboxes():
            if mb.mailbox_id == mailbox_id:
                continue
            if not getattr(mb, "is_warmup_node", False):
                continue
            if mb.provider not in self._enabled_providers:
                continue
            if provider is not None and mb.provider != provider:
                continue
            peers.append(mb.mailbox_id)
        return peers

    def _effective_ramp_day(self, st: Optional[WarmupState], today: str) -> int:
        """Рамп-день с учётом смены дня (без мутации состояния)."""
        if st is None:
            return 0
        if st.day_key != today:
            return st.ramp_day + 1
        return st.ramp_day

    def _curve_value(self, ramp_day: int) -> int:
        """Значение кривой с плато на последнем элементе."""
        if ramp_day < 0:
            ramp_day = 0
        idx = min(ramp_day, len(self._curve) - 1)
        return self._curve[idx]

    def _phase(self, ramp_day: int, rep: float) -> str:
        """Фаза прогрева по рамп-дню и репутации."""
        if rep < self._reputation_floor:
            return "paused"
        if ramp_day >= len(self._curve) - 1:
            return "steady"
        return "ramp"

    def _update_reputation(self, old: float, sent: int, failures: int) -> float:
        """Эвристика репутации по доставкам/провалам прогрева (0..1)."""
        if sent == 0 and failures == 0:
            return old
        gain = (_REP_BASE_GAIN + _REP_REPLY_GAIN * self._reply_probability) * sent
        drop = _REP_FAIL_WEIGHT * failures
        new = old + gain - drop
        return max(0.0, min(1.0, new))

    def _persist(self, mailbox_id: str, phase: str, ramp_day: int, target: int,
                 warmup_sent_today: int, rep: float, day_key: str,
                 last_warmup_at: Optional[datetime], now: datetime) -> None:
        """Сохраняет состояние прогрева через store (store ставит updated_at)."""
        self._store.upsert_warmup_state(WarmupState(
            mailbox_id=mailbox_id,
            phase=phase,
            ramp_day=ramp_day,
            warmup_target=target,
            warmup_sent_today=warmup_sent_today,
            reputation_score=rep,
            day_key=day_key,
            last_warmup_at=last_warmup_at,
        ))

    def _append_bounce(self, mailbox_id: str, provider: Optional[str], peer: str,
                       now: datetime, today: str, seq: int, error: Optional[str]) -> None:
        """Идемпотентная запись события bounce прогрева."""
        self._store.append_event(EventIn(
            dedup_key=f"warmup:bounce:{mailbox_id}:{peer}:{today}:{seq}",
            event_type="bounce",
            event_ts=now,
            mailbox_id=mailbox_id,
            provider=provider,
            detail={"warmup": True, "peer": peer, "error": error},
        ))

    def _build_message(self, mailbox_id: str, peer: str, now: datetime,
                       seq: int, today: str) -> Message:
        """Синтетическое прогрев-сообщение (peer в thread_id/idempotency)."""
        key = f"warmup:{mailbox_id}:{peer}:{today}:{seq}"
        subject, body = self._warmup_text(peer, seq)
        return Message(
            id=0,
            idempotency_key=key,
            campaign_id=0,
            recipient_id=0,
            sequence_step_id=0,
            mailbox_id=mailbox_id,
            status="sending",
            scheduled_at=now,
            claimed_at=now,
            thread_id=f"warmup:{peer}",
            subject=subject,
            body_rendered=body,
        )

    def _build_rendered(self, mailbox_id: str, peer: str) -> RenderedMessage:
        """Готовый текст прогрев-письма без плейсхолдеров (гейт не сработает)."""
        subject, body = self._warmup_text(peer, 0)
        return RenderedMessage(subject=subject, body=body, unfilled_fields=(), used_ai=False)

    @staticmethod
    def _warmup_text(peer: str, seq: int) -> tuple[str, str]:
        """Нейтральный прогрев-контент (без сырых плейсхолдеров)."""
        subject = f"Рабочий вопрос ({seq})"
        body = (
            "Добрый день!\n\n"
            "Проверяю рабочую переписку и синхронизацию по текущим задачам. "
            "Если что-то требует внимания — дайте знать.\n\n"
            "С уважением,\nкоманда"
        )
        return subject, body

    def _day_key(self, now: datetime) -> str:
        """'YYYY-MM-DD' в TZ конфига."""
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        return now.astimezone(self._tz).strftime("%Y-%m-%d")
