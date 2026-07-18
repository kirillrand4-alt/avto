"""Orchestrator — главный цикл сервиса холодной рассылки «Руспром».

Координирует независимые модули (store / sender / cadence / gates /
imap_watcher / warmup / analytics) в единый tick-цикл и обеспечивает
инварианты безопасности §5 контракта:

  1. Не слать дубль ответившему — через ``store.claim_due_messages`` (исключает
     reply-получателей в той же транзакции, что и lease) и ``imap`` (skip-цепочки).
  2. Стоп-на-bounce — ``imap`` пишет suppression + skip; оркестратор поллит IMAP
     первым шагом, до постановки/отправки новой волны.
  3. Дедуп — ``enqueue_message`` возвращает флаг ``created`` (ON CONFLICT),
     оркестратор не полагается на «проверил-потом-вставил».
  4. Гейт незаполненных {} — ловим ``PersonalizationGateError`` и непустой
     ``RenderedMessage.unfilled_fields`` → ``mark_failed(retryable=False)``:
     ни одно письмо с сырым плейсхолдером не уходит.
  5. Kill-switch — перед каждой волной ``gates.evaluate_all``; global-trip →
     ``pause_all`` + пропуск волны и прогрева; mailbox-trip → ``set_mailbox_paused``.
     Снятие паузы — только явным ``resume_all`` / решением gate.

Резюмируемость: ``bootstrap`` и каждый tick вызывают ``store.recover_stale``
(зависшие 'sending' → 'scheduled'); счётчики персистентны на стороне store.
Graceful stop: ``run`` завершает текущий tick и выходит по ``threading.Event``.
Только stdlib. Единственный писатель в БД — ``store``; оркестратор лишь
оркеструет вызовы DTO/методов и никогда не пишет в БД в обход store.
"""
from __future__ import annotations

import logging
import threading  # noqa: F401  # публичный API run(stop: threading.Event)
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING

logger = logging.getLogger("sender.orchestrator")

# --- общая для дерева иерархия исключений с self-contained fallback ---
# В собранном дереве все модули импортируют один и тот же класс (совпадает
# identity для except). Fallback держит модуль импортируемым автономно.
try:  # pragma: no cover - зависит от наличия общего модуля
    from sender.errors import (  # type: ignore
        ConfigError,
        GateTrippedError,
        PersonalizationGateError,
        RateLimitExceeded,
        SenderError,
        SendError,
        StoreError,
        SuppressedError,
        TransientError,
        ValidationError,
    )
except Exception:  # noqa: BLE001
    class SenderError(Exception):
        pass

    class ConfigError(SenderError):
        pass

    class StoreError(SenderError):
        pass

    class SuppressedError(SenderError):
        pass

    class ValidationError(SenderError):
        pass

    class PersonalizationGateError(SenderError):
        pass

    class SendError(SenderError):
        pass

    class RateLimitExceeded(SendError):
        pass

    class GateTrippedError(SenderError):
        pass

    class TransientError(SenderError):
        pass


# --- TickResult: DTO, которым владеет orchestrator (fallback при отсутствии types) ---
try:  # pragma: no cover
    from sender.dtos import TickResult  # type: ignore
except Exception:  # noqa: BLE001
    @dataclass(frozen=True)
    class TickResult:
        planned: int
        sent: int
        skipped: int
        failed: int
        inbound: int
        gates_tripped: int
        warmup_sent: int


if TYPE_CHECKING:  # аннотации без рантайм-импортов чужих модулей
    from sender.analytics import Analytics
    from sender.cadence import Cadence
    from sender.config import Config
    from sender.gates import Gates
    from sender.imap_watcher import ImapWatcher
    from sender.personalize import Personalizer
    from sender.sender import Sender
    from sender.store import Store
    from sender.dtos import (
        Campaign,
        GateDecision,
        Message,
        RenderedMessage,
        SendResult,
        SequenceStep,
    )
    from sender.warmup import Warmup


# статусы кампании, при которых допустима отправка
_SENDABLE_CAMPAIGN_STATUS = ("active",)

# дефолты (переопределяемы через config.get)
_DEFAULT_LEASE_TTL_SEC = 900          # зависшие 'sending' → 'scheduled' через 15 мин
_DEFAULT_SEND_BATCH = 100             # верхняя граница claim за один tick

_CFG_LEASE_TTL = "orchestrator.lease_ttl_sec"
_CFG_SEND_BATCH = "orchestrator.send_batch"
_CFG_ACTIVE_CAMPAIGNS = "orchestrator.active_campaigns"
_CFG_WARMUP_PROVIDERS = "warmup.enabled_providers"


class Orchestrator:
    """Композиционный корень исполнения. Не пишет в БД напрямую — только store."""

    def __init__(
        self,
        config: "Config",
        store: "Store",
        sender: "Sender",
        cadence: "Cadence",
        gates: "Gates",
        imap: "ImapWatcher",
        warmup: "Warmup",
        analytics: "Analytics",
        *,
        personalizer: "Personalizer | None" = None,
    ) -> None:
        self.config = config
        self.store = store
        self.sender = sender
        self.cadence = cadence
        self.gates = gates
        self.imap = imap
        self.warmup = warmup
        self.analytics = analytics
        self._personalizer = personalizer

        self.lease_ttl_sec = int(self._cfg(_CFG_LEASE_TTL, _DEFAULT_LEASE_TTL_SEC))
        self.send_batch = int(self._cfg(_CFG_SEND_BATCH, _DEFAULT_SEND_BATCH))
        # активные кампании: seed из конфига, доступны для внешнего управления
        self.active_campaign_ids = [int(x) for x in (self._cfg(_CFG_ACTIVE_CAMPAIGNS, []) or [])]
        self._paused = False

    # ------------------------------------------------------------------ #
    # helpers
    # ------------------------------------------------------------------ #
    def _cfg(self, key, default):
        try:
            val = self.config.get(key, default)
        except Exception:  # noqa: BLE001 - конфиг не должен ронять оркестратор
            return default
        return default if val is None else val

    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc)

    def _mailbox_ids(self) -> list[str]:
        try:
            return [mb.mailbox_id for mb in self.config.mailboxes()]
        except Exception:  # noqa: BLE001
            logger.exception("config.mailboxes() failed")
            return []

    def _active_mailbox_ids(self) -> list[str]:
        """Ящики без паузы — контракт claim_due_messages ждёт не-паузнутый набор.
        Письма с mailbox_id=NULL claim'ятся всегда; пиненные на паузнутый ящик —
        ждут снятия паузы, а не претендуют на claim и mark_skipped."""
        ids: list[str] = []
        for mid in self._mailbox_ids():
            try:
                st = self.store.get_mailbox_state(mid)
                if st is not None and bool(st.paused):
                    continue
            except Exception:  # noqa: BLE001
                logger.exception("get_mailbox_state failed mailbox=%s", mid)
            ids.append(mid)
        return ids

    def _ensure_personalizer(self):
        if self._personalizer is None:
            try:
                from sender.personalize import Personalizer  # lazy, только если не внедрён
            except Exception as e:  # noqa: BLE001
                raise ConfigError(f"personalizer is not configured/available: {e}") from e
            self._personalizer = Personalizer(self.config)
        return self._personalizer

    def _propagate_dry_run(self, dry_run: bool) -> None:
        # dry_run уровня run() управляет sender'ом — единственной точкой реальной отправки
        try:
            setattr(self.sender, "dry_run", bool(dry_run))
        except Exception:  # noqa: BLE001
            logger.warning("could not propagate dry_run to sender")

    def _safe_pause(self, mailbox_id: str, reason: str | None, *, paused: bool) -> None:
        try:
            self.store.set_mailbox_paused(mailbox_id, paused, reason)
        except Exception:  # noqa: BLE001
            logger.exception("set_mailbox_paused failed mailbox=%s paused=%s", mailbox_id, paused)

    # ------------------------------------------------------------------ #
    # lifecycle
    # ------------------------------------------------------------------ #
    def bootstrap(self) -> None:
        """init_schema + recover_stale + fail-fast проверка рендера."""
        self.store.init_schema()
        recovered = self.store.recover_stale(self.lease_ttl_sec)
        self._ensure_personalizer()  # кривая сборка падает на старте, а не в волне
        logger.info("bootstrap done: recovered_stale=%s", recovered)

    def pause_all(self, reason: str) -> None:
        self._paused = True
        for mid in self._mailbox_ids():
            self._safe_pause(mid, reason, paused=True)
        logger.warning("pause_all reason=%s", reason)

    def resume_all(self) -> None:
        self._paused = False
        for mid in self._mailbox_ids():
            self._safe_pause(mid, None, paused=False)
        logger.info("resume_all")

    # ------------------------------------------------------------------ #
    # main tick
    # ------------------------------------------------------------------ #
    def tick(self, *, now: datetime) -> TickResult:
        # 1) резюмируемость: зависшие 'sending' → 'scheduled'
        try:
            self.store.recover_stale(self.lease_ttl_sec)
        except Exception:  # noqa: BLE001
            logger.exception("recover_stale failed")

        # 2) входящие: reply/bounce/complaint из IMAP
        inbound = 0
        for mid in self._mailbox_ids():
            try:
                events = self.imap.poll_once(mid)
                inbound += len(events)
            except Exception:  # noqa: BLE001
                logger.exception("imap.poll_once failed mailbox=%s", mid)

        # 3) gates: глобальный/ящичный trip → пауза
        gates_tripped = 0
        global_tripped = False
        try:
            decisions = self.gates.evaluate_all()
            for gd in decisions:
                if gd.tripped:
                    gates_tripped += 1
                    if gd.scope == "global":
                        global_tripped = True
                        self.pause_all(f"gate_trip:{gd.metric}>{gd.threshold}")
                    elif gd.scope == "mailbox":
                        self._safe_pause(gd.target, f"gate_trip:{gd.metric}>{gd.threshold}", paused=True)
        except Exception:  # noqa: BLE001
            logger.exception("gates.evaluate_all failed")

        planned = 0
        sent = 0
        skipped = 0
        failed = 0
        warmup_sent = 0

        # 4) планирование новой волны (если не paused и не global_tripped)
        if not self._paused and not global_tripped:
            for cid in self.active_campaign_ids:
                try:
                    campaign = self.store.get_campaign(cid)
                    if campaign is None or campaign.status not in _SENDABLE_CAMPAIGN_STATUS:
                        continue
                    messages_in = self.cadence.plan_campaign(cid, now=now)
                    for msg_in in messages_in:
                        try:
                            _, created = self.store.enqueue_message(msg_in)
                            if created:
                                planned += 1
                        except Exception:  # noqa: BLE001
                            logger.exception("enqueue_message failed msg=%s", msg_in)
                except Exception:  # noqa: BLE001
                    logger.exception("plan_campaign failed campaign_id=%s", cid)

        # 5) отправка: claim + render + send
        if not self._paused and not global_tripped:
            try:
                mailboxes = self._active_mailbox_ids()
                claimed = self.store.claim_due_messages(now=now, mailbox_ids=mailboxes, limit=self.send_batch)
                for message in claimed:
                    try:
                        campaign = self.store.get_campaign(message.campaign_id)
                        recipient = self.store.get_recipient(message.recipient_id)
                        step = None
                        if campaign and recipient:
                            for s in self.store.get_steps(message.campaign_id):
                                if s.id == message.sequence_step_id:
                                    step = s
                                    break

                        if not campaign or not recipient or not step:
                            self.store.mark_skipped(message.id, "missing_data")
                            skipped += 1
                            continue

                        # рендер с гейтом незаполненных {}
                        personalizer = self._ensure_personalizer()
                        try:
                            rendered = personalizer.render(step, recipient, campaign)
                            if rendered.unfilled_fields:
                                self.store.mark_failed(
                                    message.id,
                                    f"unfilled_fields:{','.join(rendered.unfilled_fields)}",
                                    retryable=False
                                )
                                failed += 1
                                continue
                        except PersonalizationGateError as e:
                            self.store.mark_failed(message.id, str(e), retryable=False)
                            failed += 1
                            continue

                        # pick_mailbox
                        mailbox_id = self.sender.pick_mailbox(recipient, campaign)
                        if not mailbox_id:
                            self.store.mark_skipped(message.id, "no_mailbox_available")
                            skipped += 1
                            continue

                        # sender.send уже внутри делает mark_sent/mark_failed/mark_skipped
                        try:
                            result = self.sender.send(message, rendered, mailbox_id)
                            if result.ok:
                                sent += 1
                            elif result.error:
                                # sender уже сделал mark_failed/mark_skipped
                                if "skip" in result.error.lower() or "suppressed" in result.error.lower():
                                    skipped += 1
                                else:
                                    failed += 1
                            else:
                                skipped += 1
                        except (SuppressedError, GateTrippedError):
                            skipped += 1
                        except (RateLimitExceeded, TransientError):
                            # sender должен был сделать mark_failed(retryable=True), но на всякий случай
                            failed += 1
                        except Exception:  # noqa: BLE001
                            logger.exception("sender.send failed message_id=%s", message.id)
                            failed += 1

                    except Exception:  # noqa: BLE001
                        logger.exception("send loop failed message_id=%s", message.id)
                        failed += 1

            except Exception:  # noqa: BLE001
                logger.exception("claim_due_messages failed")

        # 6) warmup
        if not self._paused and not global_tripped:
            for mid in self._mailbox_ids():
                try:
                    wres = self.warmup.run_cycle(mid, now=now)
                    warmup_sent += wres.sent
                except Exception:  # noqa: BLE001
                    logger.exception("warmup.run_cycle failed mailbox=%s", mid)

        # 7) результат
        return TickResult(
            planned=planned,
            sent=sent,
            skipped=skipped,
            failed=failed,
            inbound=inbound,
            gates_tripped=gates_tripped,
            warmup_sent=warmup_sent,
        )

    # ------------------------------------------------------------------ #
    # run
    # ------------------------------------------------------------------ #
    def run(
        self,
        *,
        interval_sec: int,
        dry_run: bool = False,
        stop: "threading.Event",
    ) -> None:
        """Главный цикл с graceful stop. bootstrap вызывается вне, если нужен."""
        self._propagate_dry_run(dry_run)
        logger.info("orchestrator.run starting interval=%s dry_run=%s", interval_sec, dry_run)

        while not stop.is_set():
            t0 = time.monotonic()
            try:
                result = self.tick(now=self._now())
                logger.info(
                    "tick done: planned=%d sent=%d skipped=%d failed=%d inbound=%d gates=%d warmup=%d",
                    result.planned, result.sent, result.skipped, result.failed,
                    result.inbound, result.gates_tripped, result.warmup_sent,
                )
            except Exception:  # noqa: BLE001
                logger.exception("tick failed")

            elapsed = time.monotonic() - t0
            sleep_time = max(0.0, interval_sec - elapsed)
            if sleep_time > 0:
                stop.wait(sleep_time)

        logger.info("orchestrator.run stopped")
