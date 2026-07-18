"""
Tests for cadence module: gates, scheduling, idempotency, reply-stop.
"""

import sqlite3
import tempfile
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, date, time
from pathlib import Path
from typing import Optional

import pytest

# CONTRACT FIX: MessageIn is a §3 exchange type PRODUCED by cadence, not an
# input we mock. The previous version defined a local `MessageIn` dataclass and
# then asserted `isinstance(m, MessageIn)` on values built by the real
# implementation from `sender.types.MessageIn`. Two different classes → the
# isinstance check could never pass with a contract-correct implementation.
# We import the canonical MessageIn (re-exported by sender.cadence from
# sender.types). Mock types below are only for values we PASS IN (duck-typed),
# never for the type the module returns.
from sender.cadence import Cadence, CadenceDecision, MessageIn


# Mock types (inputs only — duck-typed by the implementation)
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
    extra: dict
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class WindowCfg:
    tz: str
    days: tuple[int, ...]
    start: str
    end: str


# Mock implementations
class MockStore:
    def __init__(self):
        self.steps = {}
        self.replies = set()
        self.events = []

    def get_steps(self, campaign_id: int) -> list[SequenceStep]:
        return self.steps.get(campaign_id, [])

    def has_reply(self, recipient_id: int, campaign_id: int) -> bool:
        return (recipient_id, campaign_id) in self.replies

    def count_events(self, *, event_type: str, campaign_id: int | None = None,
                     domain: str | None = None, since: datetime | None = None) -> int:
        count = 0
        for evt in self.events:
            if evt['type'] == event_type:
                if campaign_id and evt.get('campaign_id') != campaign_id:
                    continue
                if domain and evt.get('domain') != domain:
                    continue
                count += 1
        return count


class MockSuppression:
    def __init__(self):
        self.suppressed = set()

    def is_suppressed(self, recipient: Recipient) -> Optional[object]:
        if recipient.email in self.suppressed:
            return object()
        return None


class MockConfig:
    def __init__(self, window: WindowCfg, holidays: set[date]):
        self._window = window
        self._holidays = holidays

    def sending_window(self) -> WindowCfg:
        return self._window

    def holidays(self) -> set[date]:
        return self._holidays


# Fixtures
@pytest.fixture
def store():
    return MockStore()


@pytest.fixture
def suppression():
    return MockSuppression()


@pytest.fixture
def config():
    window = WindowCfg(
        tz="Europe/Moscow",
        days=(1, 2, 3, 4, 5),  # Mon-Fri
        start="09:30",
        end="18:00"
    )
    holidays = {date(2025, 1, 1), date(2025, 1, 7)}
    return MockConfig(window, holidays)


@pytest.fixture
def cadence(config, store, suppression):
    return Cadence(config, store, suppression)


@pytest.fixture
def recipient():
    return Recipient(
        id=1,
        email="test@example.com",
        domain="example.com",
        inn=None,
        company_name="Test Co",
        okved=None,
        segment=None,
        bitrix_id=None,
        contact_name="John Doe",
        mx_provider="other",
        valid_status="valid",
        catch_all=False,
        role_based=False,
        disposable=False,
        source="import",
        extra={},
        created_at=datetime(2025, 1, 1),
        updated_at=datetime(2025, 1, 1)
    )


@pytest.fixture
def steps():
    return [
        SequenceStep(
            id=1,
            campaign_id=1,
            step_index=0,
            delay_hours=0,
            subject_tmpl="Subject 1",
            body_tmpl="Body 1",
            engagement_gate="all",
            include_legal=True,
            active=True
        ),
        SequenceStep(
            id=2,
            campaign_id=1,
            step_index=1,
            delay_hours=48,
            subject_tmpl="Subject 2",
            body_tmpl="Body 2",
            engagement_gate="not_bounced",
            include_legal=False,
            active=True
        ),
        SequenceStep(
            id=3,
            campaign_id=1,
            step_index=2,
            delay_hours=72,
            subject_tmpl="Subject 3",
            body_tmpl="Body 3",
            engagement_gate="engaged",
            include_legal=False,
            active=True
        )
    ]


# Tests
def test_evaluate_gate_all_allows_send(cadence, recipient, steps):
    """Gate 'all' always allows send."""
    step = steps[0]
    decision = cadence.evaluate_gate(step, recipient, campaign_id=1)
    assert decision.action == 'send'
    assert decision.reason == 'gate_all'


def test_evaluate_gate_stops_on_reply(cadence, store, recipient, steps):
    """Any gate stops if recipient replied."""
    store.replies.add((recipient.id, 1))
    for step in steps:
        decision = cadence.evaluate_gate(step, recipient, campaign_id=1)
        assert decision.action == 'stop'
        assert decision.reason == 'replied'


def test_evaluate_gate_stops_on_suppression(cadence, suppression, recipient, steps):
    """Any gate stops if recipient suppressed."""
    suppression.suppressed.add(recipient.email)
    for step in steps:
        decision = cadence.evaluate_gate(step, recipient, campaign_id=1)
        assert decision.action == 'stop'
        assert decision.reason == 'suppressed'


def test_evaluate_gate_not_bounced_skips_on_bounce(cadence, store, recipient, steps):
    """Gate 'not_bounced' skips if bounce detected."""
    store.events.append({'type': 'bounce', 'campaign_id': 1, 'domain': 'example.com'})
    step = steps[1]  # not_bounced gate
    decision = cadence.evaluate_gate(step, recipient, campaign_id=1)
    assert decision.action == 'skip'
    assert decision.reason == 'bounced'


def test_evaluate_gate_engaged_skips_on_bounce(cadence, store, recipient, steps):
    """Gate 'engaged' skips if bounce detected."""
    store.events.append({'type': 'bounce', 'campaign_id': 1, 'domain': 'example.com'})
    step = steps[2]  # engaged gate
    decision = cadence.evaluate_gate(step, recipient, campaign_id=1)
    assert decision.action == 'skip'
    assert decision.reason == 'not_engaged'


def test_schedule_time_adds_delay(cadence, steps):
    """Schedule time adds step delay."""
    base = datetime(2025, 1, 15, 10, 0)
    step = steps[1]  # 48h delay
    scheduled = cadence.schedule_time(base, step)
    # Should be ~48h later (with jitter ±10%)
    delta = (scheduled - base).total_seconds() / 3600
    assert 43 <= delta <= 53  # 48 ± 10%


def test_schedule_time_shifts_past_holidays(cadence, steps):
    """Schedule time moves past holidays."""
    # Jan 1, 2025 is a holiday
    base = datetime(2025, 1, 1, 10, 0)
    step = steps[0]  # 0h delay
    scheduled = cadence.schedule_time(base, step)
    # Should shift to Jan 2 or later
    assert scheduled.date() > date(2025, 1, 1)


def test_schedule_time_shifts_into_window(cadence, steps):
    """Schedule time shifts into sending window."""
    # 7am - before window (9:30-18:00)
    base = datetime(2025, 1, 20, 7, 0)  # Monday
    step = steps[0]
    scheduled = cadence.schedule_time(base, step)
    # Should shift to 9:30
    assert scheduled.time() >= time(9, 30)


def test_schedule_time_shifts_to_next_workday(cadence, steps):
    """Schedule time shifts weekend to Monday."""
    # Saturday
    base = datetime(2025, 1, 18, 10, 0)
    step = steps[0]
    scheduled = cadence.schedule_time(base, step)
    # Should shift to Monday
    assert scheduled.date().isoweekday() == 1


def test_plan_for_recipient_generates_all_steps(cadence, store, recipient, steps):
    """Plan generates messages for all active steps."""
    store.steps[1] = steps
    now = datetime(2025, 1, 20, 10, 0)
    messages = cadence.plan_for_recipient(recipient, campaign_id=1, now=now)
    assert len(messages) == 3
    assert all(isinstance(m, MessageIn) for m in messages)


def test_plan_for_recipient_respects_gates(cadence, store, recipient, steps):
    """Plan respects engagement gates."""
    store.steps[1] = steps
    store.events.append({'type': 'bounce', 'campaign_id': 1, 'domain': 'example.com'})
    now = datetime(2025, 1, 20, 10, 0)
    messages = cadence.plan_for_recipient(recipient, campaign_id=1, now=now)
    # Should only generate first step (gate=all), others skip on bounce
    assert len(messages) == 1
    assert messages[0].sequence_step_id == 1


def test_plan_for_recipient_stops_on_reply(cadence, store, recipient, steps):
    """Plan returns empty if recipient replied."""
    store.steps[1] = steps
    store.replies.add((recipient.id, 1))
    now = datetime(2025, 1, 20, 10, 0)
    messages = cadence.plan_for_recipient(recipient, campaign_id=1, now=now)
    assert len(messages) == 0


def test_plan_for_recipient_stops_on_suppression(cadence, store, suppression, recipient, steps):
    """Plan returns empty if recipient suppressed."""
    store.steps[1] = steps
    suppression.suppressed.add(recipient.email)
    now = datetime(2025, 1, 20, 10, 0)
    messages = cadence.plan_for_recipient(recipient, campaign_id=1, now=now)
    assert len(messages) == 0


def test_idempotency_key_consistent(cadence, recipient):
    """Idempotency key is deterministic."""
    key1 = cadence._make_idempotency_key(1, recipient.id, 0)
    key2 = cadence._make_idempotency_key(1, recipient.id, 0)
    assert key1 == key2
    assert len(key1) == 64  # SHA256 hex


def test_idempotency_key_unique_per_step(cadence, recipient):
    """Idempotency key differs per step."""
    key0 = cadence._make_idempotency_key(1, recipient.id, 0)
    key1 = cadence._make_idempotency_key(1, recipient.id, 1)
    assert key0 != key1


def test_thread_id_consistent(cadence, recipient):
    """Thread ID is deterministic."""
    tid1 = cadence._make_thread_id(1, recipient.id)
    tid2 = cadence._make_thread_id(1, recipient.id)
    assert tid1 == tid2
    assert len(tid1) == 16


def test_next_step_for_returns_first_active(cadence, store, recipient, steps):
    """Next step returns first active step."""
    store.steps[1] = steps
    step = cadence.next_step_for(recipient.id, campaign_id=1)
    assert step is not None
    assert step.step_index == 0


def test_next_step_for_returns_none_on_reply(cadence, store, recipient, steps):
    """Next step returns None if replied."""
    store.steps[1] = steps
    store.replies.add((recipient.id, 1))
    step = cadence.next_step_for(recipient.id, campaign_id=1)
    assert step is None


def test_schedule_time_after_window_moves_next_day(cadence, steps):
    """Schedule after window moves to next day start."""
    # 7pm - after window (9:30-18:00)
    base = datetime(2025, 1, 20, 19, 0)  # Monday
    step = steps[0]
    scheduled = cadence.schedule_time(base, step)
    # Should be Tuesday 9:30
    assert scheduled.date() == date(2025, 1, 21)
    assert scheduled.time() >= time(9, 30)


def test_plan_for_recipient_chains_delays(cadence, store, recipient, steps):
    """Plan chains delays correctly."""
    store.steps[1] = steps
    now = datetime(2025, 1, 20, 10, 0)
    messages = cadence.plan_for_recipient(recipient, campaign_id=1, now=now)

    # First message should be scheduled around now
    assert abs((messages[0].scheduled_at - now).total_seconds()) < 3600

    # Second message should be ~48h after first
    delta = (messages[1].scheduled_at - messages[0].scheduled_at).total_seconds() / 3600
    assert 43 <= delta <= 53  # 48h ± 10% jitter


def test_evaluate_gate_progression(cadence, store, recipient, steps):
    """Gates follow all→not_bounced→engaged progression."""
    # All passes
    d1 = cadence.evaluate_gate(steps[0], recipient, campaign_id=1)
    assert d1.action == 'send'

    # not_bounced passes without bounce
    d2 = cadence.evaluate_gate(steps[1], recipient, campaign_id=1)
    assert d2.action == 'send'

    # Add bounce
    store.events.append({'type': 'bounce', 'campaign_id': 1, 'domain': 'example.com'})

    # not_bounced now skips
    d3 = cadence.evaluate_gate(steps[1], recipient, campaign_id=1)
    assert d3.action == 'skip'

    # engaged also skips
    d4 = cadence.evaluate_gate(steps[2], recipient, campaign_id=1)
    assert d4.action == 'skip'


def test_plan_respects_inactive_steps(cadence, store, recipient, steps):
    """Plan skips inactive steps."""
    inactive_step = replace(steps[1], active=False)
    store.steps[1] = [steps[0], inactive_step, steps[2]]
    now = datetime(2025, 1, 20, 10, 0)
    messages = cadence.plan_for_recipient(recipient, campaign_id=1, now=now)
    # Should only get steps 0 and 2
    assert len(messages) == 2
    assert messages[0].sequence_step_id == 1
    assert messages[1].sequence_step_id == 3


def test_schedule_time_holiday_chain(cadence, steps):
    # Contract: _shift_past_holidays "Move datetime forward if it falls on a holiday."
    # holidays = {Jan 1, Jan 7}. Jan 1 (Wed) is a holiday → shift to Jan 2 (Thu),
    # which is NOT a holiday. Jan 7 is 6 days later and does not block Jan 2.
    # The contract does not chain non-consecutive holidays, so the earliest valid
    # date is Jan 2. Implementation is correct.
    base = datetime(2025, 1, 1, 10, 0)
    step = steps[0]
    scheduled = cadence.schedule_time(base, step)
    assert scheduled.date() >= date(2025, 1, 2)  # Jan 1 holiday shifts to Jan 2 (Thu)


# ---- plan_campaign + канареечная волна ----

class PlanMockStore(MockStore):
    """MockStore + получатели/журнал для plan_campaign и канарейки."""

    def __init__(self):
        super().__init__()
        self.recipients: list[Recipient] = []
        self.appended = []
        self.last_sent_ts: Optional[datetime] = None

    def iter_recipients(self, *, valid_status=None, provider=None):
        for r in self.recipients:
            if valid_status is not None and r.valid_status != valid_status:
                continue
            yield r

    def last_event_ts(self, *, event_type, campaign_id=None):
        return self.last_sent_ts

    def append_event(self, e):
        for i, ex in enumerate(self.appended):
            if ex.dedup_key == e.dedup_key:
                return i, False
        self.appended.append(e)
        return len(self.appended), True


class CanaryConfig(MockConfig):
    def __init__(self, window, holidays, data=None):
        super().__init__(window, holidays)
        self._data = data or {}

    def get(self, key, default=None):
        return self._data.get(key, default)


def _mk_recipient(i: int, status: str = "valid") -> Recipient:
    return Recipient(
        id=i, email=f"u{i}@corp{i}.example", domain=f"corp{i}.example",
        inn=None, company_name=None, okved=None, segment=None,
        bitrix_id=None, contact_name=None, mx_provider="other",
        valid_status=status, catch_all=None, role_based=None,
        disposable=None, source=None, extra={},
        created_at=datetime(2026, 1, 1), updated_at=datetime(2026, 1, 1))


def _mk_steps(cid: int) -> list[SequenceStep]:
    return [
        SequenceStep(id=10, campaign_id=cid, step_index=0, delay_hours=0,
                     subject_tmpl="s0", body_tmpl="b0",
                     engagement_gate="all", include_legal=True, active=True),
        SequenceStep(id=11, campaign_id=cid, step_index=1, delay_hours=48,
                     subject_tmpl="s1", body_tmpl="b1",
                     engagement_gate="all", include_legal=True, active=True),
    ]


def _plan_env(canary=None, n_recipients=3):
    window = WindowCfg(tz="Europe/Moscow", days=(1, 2, 3, 4, 5),
                      start="09:30", end="18:00")
    cfg = CanaryConfig(window, set(), canary or {})
    st = PlanMockStore()
    st.steps[7] = _mk_steps(7)
    st.recipients = [_mk_recipient(i) for i in range(1, n_recipients + 1)]
    return Cadence(cfg, st, MockSuppression()), st


NOW = datetime(2026, 7, 14, 9, 0)  # вторник


def test_plan_campaign_plans_all_valid_recipients():
    """Заглушки больше нет: план = все valid-получатели × активные шаги."""
    cadence, st = _plan_env(canary={"cadence.canary_size": 0})
    st.recipients.append(_mk_recipient(99, status="invalid"))

    msgs = cadence.plan_campaign(7, now=NOW)

    assert len(msgs) == 6  # 3 получателя × 2 шага; invalid не планируется
    assert all(isinstance(m, MessageIn) for m in msgs)
    assert len({m.idempotency_key for m in msgs}) == 6


def test_plan_campaign_skips_replied():
    cadence, st = _plan_env(canary={"cadence.canary_size": 0})
    st.replies.add((2, 7))
    msgs = cadence.plan_campaign(7, now=NOW)
    assert len(msgs) == 4  # получатель 2 выпал целиком


def test_canary_limits_first_wave():
    """До canary_size планируется только канареечный срез получателей."""
    cadence, st = _plan_env(canary={"cadence.canary_size": 1})
    msgs = cadence.plan_campaign(7, now=NOW)
    # 1 получатель (оба его шага), остальные ждут канарейку
    assert len(msgs) == 2
    assert len({m.recipient_id for m in msgs}) == 1


def test_canary_hold_window_returns_nothing():
    """Канарейка дослана, DSN ещё собираем (окно hold) → волна держится."""
    cadence, st = _plan_env(canary={"cadence.canary_size": 1,
                                    "cadence.canary_hold_hours": 4})
    st.events = [{"type": "sent", "campaign_id": 7}]
    st.last_sent_ts = NOW - timedelta(hours=1)  # час назад < 4ч окна
    assert cadence.plan_campaign(7, now=NOW) == []
    assert st.appended == []  # canary_passed не выписан


def test_canary_burned_holds_wave():
    """Bounce-rate канарейки выше порога → волна НЕ открывается."""
    cadence, st = _plan_env(canary={"cadence.canary_size": 10,
                                    "cadence.canary_hold_hours": 4,
                                    "cadence.canary_max_bounce_pct": 3.0})
    st.events = ([{"type": "sent", "campaign_id": 7}] * 10
                 + [{"type": "bounce", "campaign_id": 7}] * 2)  # 20%
    st.last_sent_ts = NOW - timedelta(hours=5)  # окно прошло
    assert cadence.plan_campaign(7, now=NOW) == []
    assert st.appended == []


def test_canary_passes_and_opens_wave():
    """Чистая канарейка после окна → волна открыта + событие canary_passed."""
    cadence, st = _plan_env(canary={"cadence.canary_size": 10,
                                    "cadence.canary_hold_hours": 4,
                                    "cadence.canary_max_bounce_pct": 3.0})
    st.events = ([{"type": "sent", "campaign_id": 7}] * 100
                 + [{"type": "bounce", "campaign_id": 7}] * 1)  # 1%
    st.last_sent_ts = NOW - timedelta(hours=5)

    msgs = cadence.plan_campaign(7, now=NOW)

    assert len(msgs) == 6  # все 3 получателя
    assert len(st.appended) == 1
    ev = st.appended[0]
    assert ev.event_type == "canary_passed"
    assert ev.dedup_key == "canary_passed:7"
    assert ev.detail["rate_pct"] == 1.0


def test_canary_passed_event_short_circuits():
    """После canary_passed лимит не пересчитывается (свежий hold не мешает)."""
    cadence, st = _plan_env(canary={"cadence.canary_size": 10})
    st.events = [{"type": "canary_passed", "campaign_id": 7},
                 {"type": "sent", "campaign_id": 7}]
    st.last_sent_ts = NOW - timedelta(minutes=5)  # свежая отправка не held
    msgs = cadence.plan_campaign(7, now=NOW)
    assert len(msgs) == 6
