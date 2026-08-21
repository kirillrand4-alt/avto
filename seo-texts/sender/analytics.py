"""Read-only analytics / reporting for the Rusprom cold-email sender.

Python 3.11, standard library only. This module implements the public
``analytics`` API from §2 of the contract plus the report DTOs it owns
(``RateSnapshot``, ``CampaignReport``, ``MailboxReport``, ``WarmupReport``,
``GlobalReport``). Shared entity types (mailbox/warmup state, sequence steps)
are consumed structurally through :class:`StoreReader` so this module stays
decoupled from the other 11 modules.

Rate semantics (kept consistent across the whole system)
--------------------------------------------------------
* Every ``*_rate`` value is a **percentage** in the closed interval
  ``[0.0, 100.0]``, rounded to 4 decimal places. This matches the gate
  thresholds in config (``domain_bounce_pct: 8.0`` etc.), so a value produced
  here can be compared to a threshold without unit conversion.
* The denominator for bounce/complaint/reply rates is the number of ``sent``
  events in the same scope. Division by zero yields ``0.0`` (never raises).

Safety invariants honoured (§5)
-------------------------------
* Isolation of writes: analytics is strictly read-only. It calls only the
  read methods of the store; it never mutates state.
* Dedup (§5.3): counts are taken verbatim from the events journal, which is
  de-duplicated at the DB level via ``UNIQUE(events.dedup_key)``. Analytics
  never re-counts or re-dedupes; repeated IMAP polling of the same UID cannot
  inflate a metric.
* Stop-on-bounce accounting (§5.2): both hard (5.x.x) and soft (4.x.x) bounces
  are recorded as ``event_type='bounce'`` and both feed ``bounce_rate`` exactly
  as the gates expect.
* Kill-switch consistency (§5.5): analytics reports the *raw* rates that gates
  consume. Statistical-significance gating (``min_volume``) is the gates'
  responsibility, not analytics'; small-sample rates are reported as-is.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Iterator, Optional, Protocol, Sequence
from sender.errors import SenderError, StoreError, ValidationError  # noqa: E402

__all__ = [
    "SenderError",
    "StoreError",
    "ValidationError",
    "RateSnapshot",
    "CampaignReport",
    "MailboxReport",
    "WarmupReport",
    "GlobalReport",
    "Analytics",
    "StoreReader",
    "SCOPE_CAMPAIGN",
    "SCOPE_DOMAIN",
    "SCOPE_MAILBOX",
    "SCOPE_GLOBAL",
]

# --------------------------------------------------------------------------- #
# Exceptions (subset of the shared hierarchy declared in §2 of the contract).
# --------------------------------------------------------------------------- #


# --------------------------------------------------------------------------- #
# Constants.
# --------------------------------------------------------------------------- #

EVENT_SENT = "sent"
EVENT_DELIVERED = "delivered"
EVENT_BOUNCE = "bounce"
EVENT_COMPLAINT = "complaint"
EVENT_REPLY = "reply"
EVENT_UNSUBSCRIBE = "unsubscribe"
# open-tracking (пиксель). Справочный сигнал: в РФ прокси картинок Mail.ru/Яндекса
# искажают открытия, поэтому open НИКОГДА не участвует в гейтах/вовлечённости —
# только отдельная метрика в отчётах (OPEN-TRACKING-SPEC.md).
EVENT_OPEN = "open"
# Отказ НАШЕГО почтовика «подозрение на спам»: письмо не ушло вовсе. Не
# отбивка (та про мёртвый адрес) и не жалоба — отдельный счёт, потому что
# и причина другая, и лечение (sender/otkaz_spam.py).
EVENT_REJECT = "reject_spam"

SCOPE_CAMPAIGN = "campaign"
SCOPE_DOMAIN = "domain"
SCOPE_MAILBOX = "mailbox"
SCOPE_GLOBAL = "global"
SCOPE_STEP = "step"  # used only for per-step snapshots inside CampaignReport

_VALID_RATE_SCOPES = frozenset(
    {SCOPE_CAMPAIGN, SCOPE_DOMAIN, SCOPE_MAILBOX, SCOPE_GLOBAL}
)

_RATE_PRECISION = 4  # decimal places kept on percentage values


# --------------------------------------------------------------------------- #
# Structural read contract for the store dependency.
# --------------------------------------------------------------------------- #


class _StepLike(Protocol):
    id: int
    step_index: int


class _MailboxStateLike(Protocol):
    mailbox_id: str
    sent_today: int
    sent_total: int
    ramp_day: int
    daily_limit: int
    paused: bool


class _WarmupStateLike(Protocol):
    mailbox_id: str
    phase: str
    ramp_day: int
    warmup_sent_today: int
    reputation_score: Optional[float]


class StoreReader(Protocol):
    """Read-only surface of ``store.Store`` required by analytics.

    ``count_events`` widens the abbreviated §2 signature with ``mailbox_id`` and
    ``sequence_step_id`` filters. Both are first-class in the events schema and
    therefore expected of any conforming store:

    * ``mailbox_id``       -> index ``ix_events_mailbox(mailbox_id, event_type, event_ts)``
    * ``sequence_step_id`` -> join ``events.message_id -> messages.sequence_step_id``

    ``iter_mailbox_states`` enumerates the small ``mailbox_state`` table
    (PK ``mailbox_id``) so the global report can count active/paused mailboxes.
    A real ``Store`` satisfies this protocol structurally; the extra filter
    arguments are passed only when non-``None`` (see :meth:`Analytics._count`),
    so scopes that do not need them stay compatible with a minimal store.
    """

    def count_events(
        self,
        *,
        event_type: str,
        campaign_id: Optional[int] = None,
        domain: Optional[str] = None,
        mailbox_id: Optional[str] = None,
        sequence_step_id: Optional[int] = None,
        since: Optional[datetime] = None,
    ) -> int: ...

    def get_steps(self, campaign_id: int) -> Sequence[_StepLike]: ...

    def get_mailbox_state(self, mailbox_id: str) -> Optional[_MailboxStateLike]: ...

    def get_warmup_state(self, mailbox_id: str) -> Optional[_WarmupStateLike]: ...

    def iter_mailbox_states(self) -> Iterator[_MailboxStateLike]: ...


# --------------------------------------------------------------------------- #
# Report DTOs (owned by analytics).
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class RateSnapshot:
    scope: str
    target: str
    sent: int
    bounce: int
    complaint: int
    reply: int
    bounce_rate: float
    complaint_rate: float
    reply_rate: float


@dataclass(frozen=True)
class CampaignReport:
    campaign_id: int
    sent: int
    delivered: int
    bounced: int
    complaints: int
    replies: int
    unsubscribes: int
    bounce_rate: float
    complaint_rate: float
    reply_rate: float
    by_step: dict[int, RateSnapshot]
    # open-tracking: справочно («в РФ приблизительно»), в гейты не входит
    opens: int = 0
    open_rate: float = 0.0


@dataclass(frozen=True)
class MailboxReport:
    mailbox_id: str
    sent_today: int
    sent_total: int
    ramp_day: int
    daily_limit: int
    bounce_rate: float
    complaint_rate: float
    paused: bool
    # отказы почтовика на отправке (554 «подозрение на спам»)
    rejected: int = 0
    reject_rate: float = 0.0


@dataclass(frozen=True)
class WarmupReport:
    mailbox_id: str
    phase: str
    ramp_day: int
    warmup_sent_today: int
    reputation_score: Optional[float]


@dataclass(frozen=True)
class GlobalReport:
    total_sent: int
    total_bounced: int
    total_complaints: int
    global_bounce_rate: float
    global_complaint_rate: float
    active_mailboxes: int
    paused_mailboxes: int
    # open-tracking: справочно, НЕ вовлечённость (см. EVENT_OPEN)
    total_opens: int = 0
    global_open_rate: float = 0.0
    # отказы почтовика на отправке: письмо не ушло вовсе
    total_rejected: int = 0
    global_reject_rate: float = 0.0


@dataclass(frozen=True)
class CapacitySnapshot:
    """Ёмкость отправляющего пула (для светофора/симулятора волны, Фаза 2.1)."""
    pool: str
    mailbox_count: int
    daily_capacity: int
    sent_today: int
    remaining_today: int
    utilization_pct: float
    paused_mailboxes: int


# --------------------------------------------------------------------------- #
# Helpers.
# --------------------------------------------------------------------------- #


def _pct(part: int, whole: int) -> float:
    """Return ``part / whole`` as a percentage in [0, 100], safe on zero whole."""
    if whole <= 0:
        return 0.0
    return round(100.0 * part / whole, _RATE_PRECISION)


# --------------------------------------------------------------------------- #
# Public API.
# --------------------------------------------------------------------------- #


class Analytics:
    """Read-only reporting over the events journal and mailbox/warmup state."""

    def __init__(self, store: StoreReader) -> None:
        self._store = store
        self._sluzhebnye: Optional[list[int]] = None

    def _sluzhebnye_kampanii(self) -> list[int]:
        """Кампании, которых нет в статистике: сейчас это маяки.

        Письма-маяки уходят по тому же пути, что боевые (иначе замер папки
        ничего не стоит), но считать их отправкой нельзя — это наша
        собственная проверка. Номер кампании лежит в настройках стора, а не
        в конфиге: аналитика конфига не видит.
        """
        if self._sluzhebnye is None:
            try:
                з = self._store.get_setting("mayaki_kampaniya", None)
            except Exception:  # noqa: BLE001 - старый стор/нет таблицы
                з = None
            self._sluzhebnye = [int(з)] if з else []
        return self._sluzhebnye

    # ---- rates --------------------------------------------------------- #

    def rates(self, *, scope: str, target: str) -> RateSnapshot:
        """Return a :class:`RateSnapshot` for a scope.

        ``scope`` is one of ``campaign|domain|mailbox|global``. ``target`` is the
        campaign id (int-like), domain, or mailbox id; it is ignored for the
        ``global`` scope. Per-step rates are available via
        :meth:`campaign_report` (``by_step``).
        """
        scope_norm = str(scope).strip().lower()
        if scope_norm not in _VALID_RATE_SCOPES:
            raise ValidationError(
                f"unknown rates scope {scope!r}; "
                f"expected one of {sorted(_VALID_RATE_SCOPES)}"
            )

        if scope_norm == SCOPE_CAMPAIGN:
            cid = self._as_campaign_id(target)
            return self._snapshot(SCOPE_CAMPAIGN, cid, campaign_id=cid)
        if scope_norm == SCOPE_DOMAIN:
            dom = self._as_domain(target)
            return self._snapshot(SCOPE_DOMAIN, dom, domain=dom)
        if scope_norm == SCOPE_MAILBOX:
            mid = self._as_mailbox_id(target)
            return self._snapshot(SCOPE_MAILBOX, mid, mailbox_id=mid)

        # SCOPE_GLOBAL: no filters, target is informational only.
        display = str(target).strip() or "*"
        return self._snapshot(SCOPE_GLOBAL, display)

    # ---- campaign ------------------------------------------------------ #

    def campaign_report(self, campaign_id: int) -> CampaignReport:
        cid = self._as_campaign_id(campaign_id)

        sent = self._count(EVENT_SENT, campaign_id=cid)
        delivered = self._count(EVENT_DELIVERED, campaign_id=cid)
        bounced = self._count(EVENT_BOUNCE, campaign_id=cid)
        complaints = self._count(EVENT_COMPLAINT, campaign_id=cid)
        replies = self._count(EVENT_REPLY, campaign_id=cid)
        unsubscribes = self._count(EVENT_UNSUBSCRIBE, campaign_id=cid)
        opens = self._count(EVENT_OPEN, campaign_id=cid)

        by_step: dict[int, RateSnapshot] = {}
        for step in self._store.get_steps(cid):
            idx = int(step.step_index)
            by_step[idx] = self._snapshot(
                SCOPE_STEP,
                f"{cid}:{idx}",
                campaign_id=cid,
                sequence_step_id=int(step.id),
            )

        return CampaignReport(
            campaign_id=cid,
            sent=sent,
            delivered=delivered,
            bounced=bounced,
            complaints=complaints,
            replies=replies,
            unsubscribes=unsubscribes,
            bounce_rate=_pct(bounced, sent),
            complaint_rate=_pct(complaints, sent),
            reply_rate=_pct(replies, sent),
            by_step=by_step,
            opens=opens,
            open_rate=_pct(opens, sent),
        )

    # ---- mailbox ------------------------------------------------------- #

    def mailbox_report(
        self, mailbox_id: str, *, since: Optional[datetime] = None
    ) -> MailboxReport:
        mid = self._as_mailbox_id(mailbox_id)
        since = self._as_since(since)

        # Reputation rates come from the events journal (optionally windowed).
        sent = self._count(EVENT_SENT, mailbox_id=mid, since=since)
        bounce = self._count(EVENT_BOUNCE, mailbox_id=mid, since=since)
        complaint = self._count(EVENT_COMPLAINT, mailbox_id=mid, since=since)
        rejected = self._count(EVENT_REJECT, mailbox_id=mid, since=since)

        # Operational counters come from the persistent mailbox_state row.
        state = self._store.get_mailbox_state(mid)
        if state is None:
            return MailboxReport(
                mailbox_id=mid,
                sent_today=0,
                sent_total=0,
                ramp_day=0,
                daily_limit=0,
                bounce_rate=_pct(bounce, sent),
                complaint_rate=_pct(complaint, sent),
                paused=False,
                rejected=rejected,
                reject_rate=_pct(rejected, sent + rejected),
            )

        return MailboxReport(
            mailbox_id=mid,
            sent_today=int(state.sent_today),
            sent_total=int(state.sent_total),
            ramp_day=int(state.ramp_day),
            daily_limit=int(state.daily_limit),
            bounce_rate=_pct(bounce, sent),
            complaint_rate=_pct(complaint, sent),
            paused=bool(state.paused),
            rejected=rejected,
            reject_rate=_pct(rejected, sent + rejected),
        )

    # ---- warmup -------------------------------------------------------- #

    def warmup_report(self, mailbox_id: str) -> WarmupReport:
        mid = self._as_mailbox_id(mailbox_id)
        warm = self._store.get_warmup_state(mid)
        if warm is None:
            # Mailbox is not part of the live warmup pool.
            return WarmupReport(
                mailbox_id=mid,
                phase="none",
                ramp_day=0,
                warmup_sent_today=0,
                reputation_score=None,
            )

        rep = warm.reputation_score
        return WarmupReport(
            mailbox_id=mid,
            phase=str(warm.phase),
            ramp_day=int(warm.ramp_day),
            warmup_sent_today=int(warm.warmup_sent_today),
            reputation_score=None if rep is None else float(rep),
        )

    # ---- global -------------------------------------------------------- #

    def global_report(self, *, since: Optional[datetime] = None) -> GlobalReport:
        since = self._as_since(since)

        total_sent = self._count(EVENT_SENT, since=since)
        total_bounced = self._count(EVENT_BOUNCE, since=since)
        total_complaints = self._count(EVENT_COMPLAINT, since=since)
        total_opens = self._count(EVENT_OPEN, since=since)
        total_rejected = self._count(EVENT_REJECT, since=since)

        active = 0
        paused = 0
        for state in self._store.iter_mailbox_states():
            if bool(state.paused):
                paused += 1
            else:
                active += 1

        return GlobalReport(
            total_sent=total_sent,
            total_bounced=total_bounced,
            total_complaints=total_complaints,
            global_bounce_rate=_pct(total_bounced, total_sent),
            global_complaint_rate=_pct(total_complaints, total_sent),
            active_mailboxes=active,
            paused_mailboxes=paused,
            total_opens=total_opens,
            global_open_rate=_pct(total_opens, total_sent),
            total_rejected=total_rejected,
            # ЗНАМЕНАТЕЛЬ — ПОПЫТКИ, А НЕ ОТПРАВЛЕННОЕ. Отказ значит, что
            # письмо НЕ ушло, и в total_sent его нет: делить на отправленное
            # значило бы занижать долю тем сильнее, чем хуже дела.
            global_reject_rate=_pct(total_rejected, total_sent + total_rejected),
        )

    # ---- dashboard ----------------------------------------------------- #

    def dashboard(
        self,
        *,
        campaign_ids: Optional[Sequence[int]] = None,
        mailbox_ids: Optional[Sequence[str]] = None,
        since: Optional[datetime] = None,
    ) -> dict[str, Any]:
        """Aggregate global/mailbox/warmup/campaign reports into one dict.

        ``mailbox_ids`` defaults to every mailbox that has a state row. The
        result is plain-data (dataclasses are flattened via ``asdict``) and
        JSON-serialisable.
        """
        since = self._as_since(since)

        if mailbox_ids is None:
            resolved = [str(s.mailbox_id) for s in self._store.iter_mailbox_states()]
        else:
            resolved = [self._as_mailbox_id(m) for m in mailbox_ids]

        mailbox_reports = [
            asdict(self.mailbox_report(m, since=since)) for m in resolved
        ]
        warmup_reports = [
            asdict(self.warmup_report(m))
            for m in resolved
            if self._store.get_warmup_state(m) is not None
        ]
        campaign_reports = [
            asdict(self.campaign_report(c)) for c in (campaign_ids or ())
        ]

        return {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "since": since.isoformat() if since is not None else None,
            "global": asdict(self.global_report(since=since)),
            "mailboxes": mailbox_reports,
            "warmup": warmup_reports,
            "campaigns": campaign_reports,
        }

    # ---- internals ----------------------------------------------------- #

    def _count(
        self,
        event_type: str,
        *,
        campaign_id: Optional[int] = None,
        domain: Optional[str] = None,
        mailbox_id: Optional[str] = None,
        sequence_step_id: Optional[int] = None,
        since: Optional[datetime] = None,
    ) -> int:
        # Only forward non-None filters so unused scopes stay compatible with a
        # minimal store implementation.
        filters: dict[str, Any] = {}
        # СЛУЖЕБНЫЕ КАМПАНИИ (маяки) вычитаем всюду, КРОМЕ отчёта по самой
        # кампании: спросили про неё прямо — значит и показываем её честно.
        if campaign_id is None:
            сл = self._sluzhebnye_kampanii()
            if сл:
                filters["exclude_campaign_ids"] = сл
        if campaign_id is not None:
            filters["campaign_id"] = campaign_id
        if domain is not None:
            filters["domain"] = domain
        if mailbox_id is not None:
            filters["mailbox_id"] = mailbox_id
        if sequence_step_id is not None:
            filters["sequence_step_id"] = sequence_step_id
        if since is not None:
            filters["since"] = since
        try:
            return int(self._store.count_events(event_type=event_type, **filters))
        except TypeError:
            # Старый стор (и тестовые двойники) не знают про исключение
            # служебных кампаний. Считаем как раньше: цифра станет чуть
            # больше на число маяков, но отчёт не упадёт.
            filters.pop("exclude_campaign_ids", None)
            return int(self._store.count_events(event_type=event_type, **filters))

    def _snapshot(
        self,
        scope: str,
        target: Any,
        *,
        campaign_id: Optional[int] = None,
        domain: Optional[str] = None,
        mailbox_id: Optional[str] = None,
        sequence_step_id: Optional[int] = None,
        since: Optional[datetime] = None,
    ) -> RateSnapshot:
        kw = dict(
            campaign_id=campaign_id,
            domain=domain,
            mailbox_id=mailbox_id,
            sequence_step_id=sequence_step_id,
            since=since,
        )
        sent = self._count(EVENT_SENT, **kw)
        bounce = self._count(EVENT_BOUNCE, **kw)
        complaint = self._count(EVENT_COMPLAINT, **kw)
        reply = self._count(EVENT_REPLY, **kw)
        return RateSnapshot(
            scope=scope,
            target=str(target),
            sent=sent,
            bounce=bounce,
            complaint=complaint,
            reply=reply,
            bounce_rate=_pct(bounce, sent),
            complaint_rate=_pct(complaint, sent),
            reply_rate=_pct(reply, sent),
        )

    @staticmethod
    def _as_campaign_id(value: Any) -> int:
        if isinstance(value, bool):
            raise ValidationError("campaign id must be an int, not bool")
        try:
            cid = int(value)
        except (TypeError, ValueError):
            raise ValidationError(
                f"campaign id/target must be an int id, got {value!r}"
            ) from None
        if cid <= 0:
            raise ValidationError(f"campaign id must be positive, got {cid}")
        return cid

    @staticmethod
    def _as_mailbox_id(value: Any) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ValidationError(
                f"mailbox_id must be a non-empty str, got {value!r}"
            )
        return value.strip()

    @staticmethod
    def _as_domain(value: Any) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ValidationError(
                f"domain target must be a non-empty str, got {value!r}"
            )
        return value.strip().lower()

    @staticmethod
    def _as_since(value: Any) -> Optional[datetime]:
        if value is None:
            return None
        if isinstance(value, datetime):
            # Naive datetimes are interpreted as UTC by the store (_to_iso).
            return value
        raise ValidationError(
            f"since must be a datetime or None, got {value!r}"
        )

    # -- NEW-BACKEND: ряды/ёмкость для веб-панели (Фаза 2.1) -------------- #

    def rate_series(
        self, *, scope: str, target: str, days: int = 7, bucket: str = "day"
    ) -> list[RateSnapshot]:
        """Временной ряд метрик по дням (для sparkline/графиков).

        count_events умеет only-``since`` (без ``until``), поэтому дневное окно
        считается как разность двух ``since``-запросов: N(день) = N(с начала дня)
        − N(со следующего дня). Возвращает ``days`` снимков от старого к новому.
        """
        scope_norm = str(scope).strip().lower()
        if scope_norm not in _VALID_RATE_SCOPES:
            raise ValidationError(f"unknown rate_series scope {scope!r}")
        kw: dict[str, Any] = {}
        if scope_norm == SCOPE_CAMPAIGN:
            kw["campaign_id"] = self._as_campaign_id(target)
        elif scope_norm == SCOPE_DOMAIN:
            kw["domain"] = self._as_domain(target)
        elif scope_norm == SCOPE_MAILBOX:
            kw["mailbox_id"] = self._as_mailbox_id(target)
        # global: без фильтров

        now = datetime.now(timezone.utc)
        day0 = datetime(now.year, now.month, now.day, tzinfo=timezone.utc)
        out: list[RateSnapshot] = []
        for i in range(days - 1, -1, -1):
            start = day0 - timedelta(days=i)
            end = start + timedelta(days=1)

            def day_count(ev: str) -> int:
                return self._count(ev, since=start, **kw) - self._count(ev, since=end, **kw)

            sent = day_count(EVENT_SENT)
            bounce = day_count(EVENT_BOUNCE)
            complaint = day_count(EVENT_COMPLAINT)
            reply = day_count(EVENT_REPLY)
            out.append(RateSnapshot(
                scope=scope_norm, target=start.strftime("%Y-%m-%d"),
                sent=sent, bounce=bounce, complaint=complaint, reply=reply,
                bounce_rate=_pct(bounce, sent), complaint_rate=_pct(complaint, sent),
                reply_rate=_pct(reply, sent),
            ))
        return out

    def capacity_report(self, pool: str, *, mailbox_ids: Sequence[str]) -> CapacitySnapshot:
        """Ёмкость пула по его ящикам (mailbox_ids передаёт вызывающий из config)."""
        cap = sent = paused = 0
        counted = 0
        for mid in mailbox_ids:
            state = self._store.get_mailbox_state(mid)
            if state is None:
                continue
            counted += 1
            cap += int(state.daily_limit)
            sent += int(state.sent_today)
            if bool(state.paused):
                paused += 1
        remaining = max(0, cap - sent)
        util = round(100.0 * sent / cap, _RATE_PRECISION) if cap > 0 else 0.0
        return CapacitySnapshot(
            pool=str(pool), mailbox_count=counted, daily_capacity=cap,
            sent_today=sent, remaining_today=remaining, utilization_pct=util,
            paused_mailboxes=paused,
        )
