"""
Cadence engine: touch sequencing with engagement gates, reply-stop, holidays/windows.
Schedules next steps, evaluates gates, plans campaigns.
"""

import hashlib
import random
from dataclasses import dataclass
from datetime import datetime, timedelta, date, time
from typing import Optional, Protocol

from .dtos import (
    SequenceStep, Recipient, MessageIn, CadenceDecision,
    WindowCfg, GatesCfg, EventIn
)


class SenderError(Exception):
    pass


class StoreProtocol(Protocol):
    def get_steps(self, campaign_id: int) -> list[SequenceStep]: ...
    def has_reply(self, recipient_id: int, campaign_id: int) -> bool: ...
    def count_events(self, *, event_type: str, campaign_id: int | None = None,
                     domain: str | None = None, since: datetime | None = None) -> int: ...
    def iter_recipients(self, *, valid_status: str | None = None,
                        provider: str | None = None): ...
    def last_event_ts(self, *, event_type: str,
                      campaign_id: int | None = None) -> Optional[datetime]: ...
    def append_event(self, e) -> tuple[int, bool]: ...


class SuppressionProtocol(Protocol):
    def is_suppressed(self, recipient) -> Optional[object]: ...


class ConfigProtocol(Protocol):
    def sending_window(self) -> WindowCfg: ...
    def holidays(self) -> set[date]: ...


class Cadence:
    """
    Manages touch sequences with engagement gating:
    - all → not_bounced → engaged progression
    - reply → stop entire chain
    - respects sending windows and holidays
    - schedules next step with randomization
    """

    def __init__(self, config: ConfigProtocol, store: StoreProtocol,
                 suppression: SuppressionProtocol):
        self._config = config
        self._store = store
        self._suppression = suppression

    def plan_campaign(self, campaign_id: int, *, now: datetime) -> list[MessageIn]:
        """
        Expand campaign steps into message queue.
        Returns MessageIn DTOs ready for store.enqueue_message.
        Skips suppressed recipients and those who replied.

        Канареечная волна: пока кампания не отправила canary_size писем и их
        hard-bounce-rate не измерен после окна ожидания DSN, планируется только
        канареечный срез получателей (см. _canary_limit). Раньше пауза gates
        била уже ПОСЛЕ удара первой полной волной по репутации.
        """
        steps = self._store.get_steps(campaign_id)
        if not steps:
            return []

        limit = self._canary_limit(campaign_id, now=now)  # None=открыто, 0=держим, N=срез
        if limit == 0:
            return []

        messages: list[MessageIn] = []
        planned_recipients = 0
        for recipient in self._store.iter_recipients(valid_status="valid"):
            batch = self.plan_for_recipient(recipient, campaign_id, now=now)
            if not batch:
                continue
            messages.extend(batch)
            planned_recipients += 1
            # лимит по ПОЛУЧАТЕЛЯМ (≈ step-0 письмам волны), чтобы не резать
            # цепочку конкретного получателя посередине
            if limit is not None and planned_recipients >= limit:
                break
        return messages

    def _canary_limit(self, campaign_id: int, *, now: datetime) -> Optional[int]:
        """Сколько получателей можно планировать сейчас.

        None — канарейка пройдена/выключена, планируем всех;
        0 — держим волну (канарейка в полёте или сгорела);
        N>0 — добираем канареечный срез.

        Все состояния выводятся из журнала событий (стейтлесс, резюмируемо):
        «пройдено» помечается событием canary_passed (дедуп по ON CONFLICT).
        """
        size = int(self._cfg_get("cadence.canary_size", 150))
        if size <= 0:
            return None  # канарейка выключена конфигом

        if self._store.count_events(event_type="canary_passed",
                                    campaign_id=campaign_id) > 0:
            return None

        sent = self._store.count_events(event_type="sent", campaign_id=campaign_id)
        if sent < size:
            return size - sent  # добор канарейки

        # канарейка дослана — ждём окно сбора DSN от последней отправки
        hold_hours = float(self._cfg_get("cadence.canary_hold_hours", 4.0))
        last_sent = self._store.last_event_ts(event_type="sent",
                                              campaign_id=campaign_id)
        if last_sent is None:
            return 0
        if now - last_sent < timedelta(hours=hold_hours):
            return 0

        max_pct = float(self._cfg_get("cadence.canary_max_bounce_pct", 3.0))
        bounced = self._store.count_events(event_type="bounce",
                                           campaign_id=campaign_id)
        rate = 100.0 * bounced / sent if sent else 0.0
        if rate > max_pct:
            # сгорела: волну держим; домены/ящики параллельно тормозят gates,
            # снятие — оператором (resume/ручной canary_passed)
            return 0

        self._store.append_event(EventIn(
            dedup_key=f"canary_passed:{campaign_id}",
            event_type="canary_passed",
            event_ts=now,
            campaign_id=campaign_id,
            detail={"sent": sent, "bounced": bounced, "rate_pct": round(rate, 4)},
        ))
        return None

    def _cfg_get(self, key: str, default):
        """config.get с фолбэком: конфиги без .get (фейки в тестах) не роняют."""
        try:
            val = self._config.get(key, default)
        except (AttributeError, TypeError):
            return default
        return default if val is None else val

    def next_step_for(self, recipient_id: int, campaign_id: int) -> Optional[SequenceStep]:
        """
        Find next step for recipient in campaign sequence.
        Returns None if chain complete or stopped.
        """
        if self._store.has_reply(recipient_id, campaign_id):
            return None

        steps = self._store.get_steps(campaign_id)
        if not steps:
            return None

        # Sort and find first active step not yet sent
        steps = sorted([s for s in steps if s.active], key=lambda s: s.step_index)
        # Would need to check which steps already sent - simplified here
        return steps[0] if steps else None

    def evaluate_gate(self, step: SequenceStep, recipient: Recipient,
                      campaign_id: int) -> CadenceDecision:
        """
        Evaluate engagement gate for step.
        Returns decision: send|skip|stop

        Gate progression:
        - all: no filtering
        - not_bounced: requires no hard bounce
        - engaged: requires delivery confirmation

        Always stop if recipient replied.
        """
        # Check reply first - hard stop
        if self._store.has_reply(recipient.id, campaign_id):
            return CadenceDecision(action='stop', reason='replied')

        # Check suppression
        if self._suppression.is_suppressed(recipient):
            return CadenceDecision(action='stop', reason='suppressed')

        gate = step.engagement_gate

        if gate == 'all':
            return CadenceDecision(action='send', reason='gate_all')

        # For not_bounced and engaged, check bounce events
        bounce_count = self._store.count_events(
            event_type='bounce',
            campaign_id=campaign_id,
            domain=recipient.domain
        )

        if gate == 'not_bounced':
            # Check if this specific recipient bounced
            # Simplified: check domain bounce rate
            if bounce_count > 0:
                return CadenceDecision(action='skip', reason='bounced')
            return CadenceDecision(action='send', reason='gate_not_bounced')

        if gate == 'engaged':
            # Engaged requires delivery (no bounce) and ideally open/click
            # Simplified: require no bounces and some sent messages
            if bounce_count > 0:
                return CadenceDecision(action='skip', reason='not_engaged')
            # Would check for open/click events in production
            return CadenceDecision(action='send', reason='gate_engaged')

        # Unknown gate
        return CadenceDecision(action='skip', reason='unknown_gate')

    def schedule_time(self, base: datetime, step: SequenceStep) -> datetime:
        """
        Calculate scheduled send time for step.
        - Adds delay_hours from step
        - Adds randomization (±10%)
        - Shifts past holidays
        - Shifts into sending window
        Returns UTC datetime.
        """
        # Add base delay
        hours = step.delay_hours
        # Add jitter: ±10%
        jitter = random.uniform(-0.1, 0.1) * hours
        total_hours = hours + jitter

        scheduled = base + timedelta(hours=total_hours)

        # Shift past holidays
        scheduled = self._shift_past_holidays(scheduled)

        # Shift into window
        scheduled = self._shift_into_window(scheduled)

        return scheduled

    def _shift_past_holidays(self, dt: datetime) -> datetime:
        """Move datetime forward if it falls on a holiday."""
        holidays = self._config.holidays()
        current = dt

        while current.date() in holidays:
            # Move to next day at same time
            current = current + timedelta(days=1)

        return current

    def _shift_into_window(self, dt: datetime) -> datetime:
        """Shift datetime into sending window if outside."""
        window = self._config.sending_window()

        # Convert to window timezone (simplified - assume UTC input)
        # In production, would use pytz/zoneinfo
        current_date = dt.date()
        weekday = current_date.isoweekday()  # ISO: 1=Monday

        # Check if weekday allowed
        if weekday not in window.days:
            # Find next allowed day
            days_ahead = 1
            while (current_date + timedelta(days=days_ahead)).isoweekday() not in window.days:
                days_ahead += 1
            dt = datetime.combine(
                current_date + timedelta(days=days_ahead),
                self._parse_time(window.start)
            )
            return dt

        # Parse window times
        start_time = self._parse_time(window.start)
        end_time = self._parse_time(window.end)
        current_time = dt.time()

        # Before window - move to start
        if current_time < start_time:
            return datetime.combine(current_date, start_time)

        # After window - move to next day start
        if current_time > end_time:
            next_date = current_date + timedelta(days=1)
            next_weekday = next_date.isoweekday()
            if next_weekday not in window.days:
                days_ahead = 1
                while (next_date + timedelta(days=days_ahead)).isoweekday() not in window.days:
                    days_ahead += 1
                next_date = next_date + timedelta(days=days_ahead)
            return datetime.combine(next_date, start_time)

        # Inside window
        return dt

    @staticmethod
    def _parse_time(time_str: str) -> time:
        """Parse HH:MM time string."""
        hours, minutes = map(int, time_str.split(':'))
        return time(hours, minutes)

    def plan_for_recipient(self, recipient: Recipient, campaign_id: int, *,
                           now: datetime) -> list[MessageIn]:
        """
        Generate message queue entries for recipient in campaign.
        Applies gates, generates idempotency keys, schedules times.
        """
        steps = self._store.get_steps(campaign_id)
        if not steps:
            return []

        # Check if already replied - stop chain
        if self._store.has_reply(recipient.id, campaign_id):
            return []

        # Check suppression
        if self._suppression.is_suppressed(recipient):
            return []

        steps = sorted([s for s in steps if s.active], key=lambda s: s.step_index)
        messages = []
        base_time = now

        for step in steps:
            # Evaluate gate
            decision = self.evaluate_gate(step, recipient, campaign_id)
            if decision.action == 'stop':
                break
            if decision.action == 'skip':
                continue

            # Generate idempotency key
            idem_key = self._make_idempotency_key(campaign_id, recipient.id, step.step_index)

            # Schedule time
            scheduled = self.schedule_time(base_time, step)

            # Generate thread_id for first touch
            thread_id = self._make_thread_id(campaign_id, recipient.id) if step.step_index == 0 else None

            # Create MessageIn with proper dataclass constructor
            msg = self._create_message_in(
                idempotency_key=idem_key,
                campaign_id=campaign_id,
                recipient_id=recipient.id,
                sequence_step_id=step.id,
                scheduled_at=scheduled,
                thread_id=thread_id
            )
            messages.append(msg)

            # Next step scheduled relative to this one
            base_time = scheduled

        return messages

    @staticmethod
    def _create_message_in(idempotency_key: str, campaign_id: int, recipient_id: int,
                           sequence_step_id: int, scheduled_at: datetime,
                           thread_id: Optional[str]) -> MessageIn:
        """Create MessageIn instance matching the test's expected type."""
        return MessageIn(
            idempotency_key=idempotency_key,
            campaign_id=campaign_id,
            recipient_id=recipient_id,
            sequence_step_id=sequence_step_id,
            scheduled_at=scheduled_at,
            thread_id=thread_id
        )

    @staticmethod
    def _make_idempotency_key(campaign_id: int, recipient_id: int, step_index: int) -> str:
        """Generate SHA256 idempotency key for message."""
        payload = f"{campaign_id}|{recipient_id}|{step_index}"
        return hashlib.sha256(payload.encode()).hexdigest()

    @staticmethod
    def _make_thread_id(campaign_id: int, recipient_id: int) -> str:
        """Generate thread ID for message chain."""
        payload = f"thread:{campaign_id}:{recipient_id}"
        return hashlib.sha256(payload.encode()).hexdigest()[:16]
