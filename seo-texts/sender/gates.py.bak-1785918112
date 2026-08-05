# FILE: sender/gates.py
"""Kill-switch gates for the Rusprom cold-outreach sender.

The module owns the reputation kill-switch. It reads the append-only ``events``
journal through ``store`` and computes bounce / complaint rates per recipient
domain, per sending mailbox and globally, comparing them against the thresholds
in :class:`GatesCfg`. A minimum-volume guard prevents tripping on small samples.

Safety contract (interface spec §5.5):
    * Tripping only pauses; it never resumes. Resuming happens exclusively via
      an explicit external action (``orchestrator.resume_all`` /
      ``store.set_mailbox_paused(False)``). ``evaluate_all`` therefore never
      emits ``action='resume'`` and never removes a suppression / unpauses a
      mailbox.
    * All pauses go through ``store``:
        - mailbox  -> ``store.set_mailbox_paused``
        - domain   -> domain-scoped ``store.suppression_add`` (which
          ``store.claim_due_messages`` already honours, so a paused domain can
          no longer be dequeued).
    * The global decision is returned for the orchestrator to act on
      (``pause_all``); gates does not pause every mailbox itself on a global
      trip, keeping responsibilities isolated.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Iterator, Optional
from sender.errors import GateTrippedError, SenderError  # noqa: E402

logger = logging.getLogger("sender.gates")

if TYPE_CHECKING:  # pragma: no cover - typing only, resolved in the full project
    from .config import Config
    from .store import Store


# --------------------------------------------------------------------------
# Shared contract types. In the full 12-module project these live in
# ``sender.errors`` / ``sender.types``; the try/except keeps this module (and
# its tests) runnable standalone with identical definitions.
# --------------------------------------------------------------------------


try:  # pragma: no cover - import machinery
    from .dtos import GateDecision, GatesCfg, SuppressionIn  # type: ignore
except Exception:  # noqa: BLE001
    @dataclass(frozen=True)
    class GatesCfg:
        domain_bounce_pct: float
        domain_complaint_pct: float
        mailbox_bounce_pct: float
        global_complaint_pct: float
        min_volume: int
        provider_bounce_pct: float = 2.5

    @dataclass(frozen=True)
    class GateDecision:
        scope: str            # domain|mailbox|global
        target: str
        tripped: bool
        metric: str           # bounce_rate|complaint_rate
        value: float
        threshold: float
        action: str           # none|pause|resume

    @dataclass(frozen=True)
    class SuppressionIn:
        scope: str            # email|domain|inn
        value: str
        reason: str           # competitor|unsubscribe|complaint|bounce_hard|manual|dsn
        source: str = ""
        campaign_id: Optional[int] = None
        expires_at: Optional[datetime] = None


__all__ = [
    "Gates",
    "GateDecision",
    "GatesCfg",
    "SuppressionIn",
    "GateTrippedError",
    "SenderError",
]

_GLOBAL_TARGET = "*"


def _norm(domain: str) -> str:
    """Normalise a domain the same way the rest of the pipeline stores it."""
    return (domain or "").strip().lower()


class Gates:
    """Reputation kill-switch.

    Parameters
    ----------
    config:
        Provides :meth:`gates` (:class:`GatesCfg`) and :meth:`mailboxes`
        (objects exposing ``mailbox_id``).
    store:
        The only DB writer. Gates uses ``count_events``, ``iter_recipients``,
        ``set_mailbox_paused`` and ``suppression_add``.
    """

    def __init__(self, config: "Config", store: "Store") -> None:
        self._config = config
        self._store = store
        self._cfg: GatesCfg = config.gates()

    def _since(self) -> Optional[datetime]:
        """Начало окна метрик (ревью, подтверждено): без окна историческая
        «чистая» масса разбавляла знаменатель и свежий всплеск не пробивал
        порог. window_days=0 — прежнее поведение (вся история)."""
        days = int(getattr(self._cfg, "window_days", 14) or 0)
        if days <= 0:
            return None
        return datetime.now(timezone.utc) - timedelta(days=days)

    # ---- public API ------------------------------------------------------

    def check_domain(self, domain: str, campaign_id: int | None = None) -> GateDecision:
        """Evaluate the bounce and complaint gates for a recipient domain.

        Returns the tripped decision (bounce has priority) or, if neither
        trips, the untripped bounce decision. Never mutates state.
        """
        bounce, complaint = self._domain_metrics(domain, campaign_id)
        if bounce.tripped:
            return bounce
        if complaint.tripped:
            return complaint
        return bounce

    def check_mailbox(self, mailbox_id: str) -> GateDecision:
        """Evaluate the per-mailbox hard-bounce gate. Never mutates state."""
        sent = self._count("sent", mailbox_id=mailbox_id, since=self._since())
        bounce = self._count("bounce", mailbox_id=mailbox_id, since=self._since())
        return self._decide(
            scope="mailbox",
            target=mailbox_id,
            metric="bounce_rate",
            numerator=bounce,
            sent=sent,
            threshold=self._cfg.mailbox_bounce_pct,
        )

    def check_global(self) -> GateDecision:
        """Evaluate the global complaint gate (the hard stop). No mutation."""
        sent = self._count("sent", since=self._since())
        complaint = self._count("complaint", since=self._since())
        return self._decide(
            scope="global",
            target=_GLOBAL_TARGET,
            metric="complaint_rate",
            numerator=complaint,
            sent=sent,
            threshold=self._cfg.global_complaint_pct,
        )

    def check_recipient_provider(self, provider: str) -> GateDecision:
        """Bounce-гейт × провайдер получателя (recipients.mx_provider).

        Репутация у Mail.ru и Яндекса раздельная: 74% базы сидит на двух
        провайдерах, и всплеск баунсов по одному из них — сигнал раньше, чем
        средняя по больнице. Never mutates state: авто-suppress провайдера
        уровня mail.ru снёс бы половину базы, поэтому trip этого скоупа
        только репортится (orchestrator логирует, notify-фича алертит),
        решение — за оператором.
        """
        provider = (provider or "").strip().lower()
        sent = self._count("sent", recipient_provider=provider, since=self._since())
        bounce = self._count("bounce", recipient_provider=provider, since=self._since())
        threshold = getattr(self._cfg, "provider_bounce_pct", 2.5)
        return self._decide(
            scope="recipient_provider",
            target=provider,
            metric="bounce_rate",
            numerator=bounce,
            sent=sent,
            threshold=threshold,
        )

    def evaluate_all(self) -> list[GateDecision]:
        """Evaluate every scope and apply pauses for tripped mailboxes/domains.

        Order: global first, then each configured mailbox, then each active
        recipient domain. Side effects:
            * tripped mailbox -> ``store.set_mailbox_paused(.., True, 'gate_bounce')``
            * tripped domain  -> domain-scoped ``store.suppression_add``
        The global decision is returned (untouched) for the orchestrator to
        act on. Nothing is ever resumed here, and calls are idempotent: the
        underlying store operations use upsert / ``ON CONFLICT DO NOTHING``.
        """
        decisions: list[GateDecision] = []

        # 1) global — reported only; orchestrator owns pause_all.
        decisions.append(self.check_global())

        # 2) mailboxes
        for mb in self._config.mailboxes():
            decision = self.check_mailbox(mb.mailbox_id)
            if decision.tripped:
                self._store.set_mailbox_paused(mb.mailbox_id, True, "gate_bounce")
            decisions.append(decision)

        # 3) domains — the min-volume guard inside _decide filters out noise.
        #    Ревью (подтверждено): раньше на каждый домен шло 3 COUNT-запроса
        #    (500 доменов = 1500 SQL за тик) — теперь один GROUP BY; фолбэк
        #    на поштучный путь для store-фейков без агрегата.
        grouped = None
        counter = getattr(self._store, "count_events_grouped", None)
        if callable(counter):
            try:
                raw = counter(by="domain",
                              event_types=("sent", "bounce", "complaint"),
                              since=self._since())
                # ключи → канон домена (легаси-строки могли быть в верхнем
                # регистре), дубликаты суммируются
                grouped = {}
                for k, v in raw.items():
                    slot = grouped.setdefault(_norm(k), {})
                    for et, n in v.items():
                        slot[et] = slot.get(et, 0) + int(n)
            except Exception:  # noqa: BLE001
                logger.exception("count_events_grouped failed — поштучный путь")
                grouped = None
        for domain in self._active_domains():
            if grouped is not None:
                g = grouped.get(domain, {})
                sent = int(g.get("sent", 0))
                bounce = self._decide(
                    scope="domain", target=domain, metric="bounce_rate",
                    numerator=int(g.get("bounce", 0)), sent=sent,
                    threshold=self._cfg.domain_bounce_pct)
                complaint = self._decide(
                    scope="domain", target=domain, metric="complaint_rate",
                    numerator=int(g.get("complaint", 0)), sent=sent,
                    threshold=self._cfg.domain_complaint_pct)
            else:
                bounce, complaint = self._domain_metrics(domain)
            if bounce.tripped:
                self._pause_domain(domain, "bounce_rate")
            if complaint.tripped:
                self._pause_domain(domain, "complaint_rate")
            decisions.append(bounce)
            decisions.append(complaint)

        # 4) recipient providers — report-only (см. check_recipient_provider):
        #    авто-пауза «всего Mail.ru» опасна, trip отдаётся наверх как сигнал.
        for provider in self._active_providers():
            decisions.append(self.check_recipient_provider(provider))

        return decisions

    def trip(self, scope: str, target: str, reason: str) -> None:
        """Manual kill-switch. Applies a pause through ``store`` for ``scope``.

        scope:
            ``mailbox`` -> pause a single mailbox.
            ``domain``  -> suppress a domain.
            ``global``  -> pause every configured mailbox.
        Raises ``ValueError`` for an unknown scope. This only pauses; there is
        no ``untrip`` — resuming is always explicit.
        """
        scope = (scope or "").strip().lower()
        reason = reason or "manual"
        if scope == "mailbox":
            self._store.set_mailbox_paused(target, True, reason)
        elif scope == "domain":
            self._pause_domain(_norm(target), "manual", reason=reason)
        elif scope == "global":
            for mb in self._config.mailboxes():
                self._store.set_mailbox_paused(mb.mailbox_id, True, reason)
        else:
            raise ValueError(f"unknown gate scope: {scope!r}")

    # ---- internals -------------------------------------------------------

    def _domain_metrics(
        self, domain: str, campaign_id: int | None = None
    ) -> tuple[GateDecision, GateDecision]:
        """Compute the (bounce, complaint) domain decisions sharing one ``sent``
        read to keep the event queries minimal."""
        domain = _norm(domain)
        sent = self._count("sent", domain=domain, campaign_id=campaign_id, since=self._since())
        bounce = self._count("bounce", domain=domain, campaign_id=campaign_id, since=self._since())
        complaint = self._count("complaint", domain=domain, campaign_id=campaign_id, since=self._since())
        b = self._decide(
            scope="domain", target=domain, metric="bounce_rate",
            numerator=bounce, sent=sent, threshold=self._cfg.domain_bounce_pct,
        )
        c = self._decide(
            scope="domain", target=domain, metric="complaint_rate",
            numerator=complaint, sent=sent, threshold=self._cfg.domain_complaint_pct,
        )
        return b, c

    def _decide(
        self,
        *,
        scope: str,
        target: str,
        metric: str,
        numerator: int,
        sent: int,
        threshold: float,
    ) -> GateDecision:
        """Build a decision. Tripped iff the sample is statistically
        significant (``sent >= min_volume``) and the rate strictly exceeds the
        threshold."""
        rate = (100.0 * numerator / sent) if sent > 0 else 0.0
        significant = sent >= self._cfg.min_volume
        tripped = significant and rate > threshold
        return GateDecision(
            scope=scope,
            target=target,
            tripped=tripped,
            metric=metric,
            value=round(rate, 4),
            threshold=float(threshold),
            action="pause" if tripped else "none",
        )

    def _count(
        self,
        event_type: str,
        *,
        domain: str | None = None,
        campaign_id: int | None = None,
        mailbox_id: str | None = None,
        recipient_provider: str | None = None,
        since: datetime | None = None,
    ) -> int:
        """Thin wrapper over ``store.count_events``.

        ``mailbox_id`` / ``recipient_provider`` are optional filters. If the
        store predates one (raises ``TypeError``), that gate degrades to a
        no-op rather than crashing.
        """
        kwargs: dict[str, object] = {"event_type": event_type}
        if domain is not None:
            kwargs["domain"] = domain
        if campaign_id is not None:
            kwargs["campaign_id"] = campaign_id
        if since is not None:
            kwargs["since"] = since
        if mailbox_id is not None or recipient_provider is not None:
            if mailbox_id is not None:
                kwargs["mailbox_id"] = mailbox_id
            if recipient_provider is not None:
                kwargs["recipient_provider"] = recipient_provider
            try:
                return int(self._store.count_events(**kwargs))
            except TypeError:
                # Ревью (подтверждено): молчаливый 0 превращал гейт в no-op
                # незаметно. Считаем 0, но кричим в лог.
                logger.warning(
                    "count_events не принял фильтры %s — гейт деградировал в 0",
                    sorted(kwargs))
                return 0
        return int(self._store.count_events(**kwargs))

    def _active_domains(self) -> Iterator[str]:
        """Yield distinct, normalised recipient domains."""
        seen: set[str] = set()
        for r in self._store.iter_recipients():
            d = _norm(getattr(r, "domain", "") or "")
            if d and d not in seen:
                seen.add(d)
                yield d

    def _active_providers(self) -> Iterator[str]:
        """Yield distinct recipient mx_provider values (yandex/mailru/…)."""
        seen: set[str] = set()
        for r in self._store.iter_recipients():
            p = (getattr(r, "mx_provider", "") or "").strip().lower()
            if p and p not in seen:
                seen.add(p)
                yield p

    def _pause_domain(self, domain: str, metric: str, *, reason: str | None = None) -> None:
        """Pause a domain by adding it to suppression (idempotent via the
        store's ``ON CONFLICT DO NOTHING``)."""
        if reason is None:
            reason = "complaint" if metric == "complaint_rate" else "bounce_hard"
        self._store.suppression_add(
            SuppressionIn(
                scope="domain",
                value=_norm(domain),
                reason=reason,
                source=f"gate:{metric}",
            )
        )

    # -- NEW-BACKEND: live-снимок сработавших гейтов (Фаза 2.1) ----------- #

    def active_trips(self) -> list[GateDecision]:
        """Список сейчас сработавших (tripped) гейтов со всеми полями решения —
        для баннера «почему на паузе». Live-оценка БЕЗ побочек: ничего не пишет
        и не паузит (в отличие от ``evaluate_all``). Переиспользует check-методы.
        """
        trips: list[GateDecision] = []
        g = self.check_global()
        if g.tripped:
            trips.append(g)
        try:
            mailboxes = list(self._config.mailboxes())
        except Exception:  # noqa: BLE001
            mailboxes = []
        for mb in mailboxes:
            d = self.check_mailbox(mb.mailbox_id)
            if d.tripped:
                trips.append(d)
        for domain in self._active_domains():
            bounce, complaint = self._domain_metrics(domain)
            if bounce.tripped:
                trips.append(bounce)
            if complaint.tripped:
                trips.append(complaint)
        for provider in self._active_providers():
            d = self.check_recipient_provider(provider)
            if d.tripped:
                trips.append(d)
        return trips
