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

        # 2) входящие: reply
