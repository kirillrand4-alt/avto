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
     ``RenderedMessage.unfilled_fields`` → очередь «дозаполнить данные»
     (``mark_needs_data``, §3 BASE-MERGE):
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
from sender.errors import ConfigError, GateTrippedError, PersonalizationGateError, RateLimitExceeded, SendError, SenderError, StoreError, SuppressedError, TransientError, ValidationError  # noqa: E402

logger = logging.getLogger("sender.orchestrator")

# --- общая для дерева иерархия исключений с self-contained fallback ---
# В собранном дереве все модули импортируют один и тот же класс (совпадает
# identity для except). Fallback держит модуль импортируемым автономно.


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
        queued: int = 0


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
        notifier=None,
        cards=None,
        confirm=None,
    ) -> None:
        self.config = config
        self.store = store
        self.sender = sender
        # Режим «подтвердить отправку»: если confirm задан и confirm.mode()!='off',
        # оркестратор НЕ шлёт письмо напрямую, а кладёт его в очередь подтверждений
        # оператора (confirm_reviews, статус pending_review) с инфо-панелью. Реальный
        # SMTP — только после ручного approve (и только при confirm.live_send). Без
        # этого исходящие уходили мимо очереди (инцидент 2026-07-24).
        self._confirm = confirm
        # Гейт направлений §4, точка 1 (сборка очереди): CompanyCards или None
        self._cards = cards
        self.cadence = cadence
        self.gates = gates
        self.imap = imap
        self.warmup = warmup
        self.analytics = analytics
        self._personalizer = personalizer
        self._notifier = notifier  # опц. sender.notify.Notifier (гейт-трипы в Telegram)

        self.lease_ttl_sec = int(self._cfg(_CFG_LEASE_TTL, _DEFAULT_LEASE_TTL_SEC))
        self.send_batch = int(self._cfg(_CFG_SEND_BATCH, _DEFAULT_SEND_BATCH))
        # активные кампании: seed из конфига, доступны для внешнего управления
        self.active_campaign_ids = [int(x) for x in (self._cfg(_CFG_ACTIVE_CAMPAIGNS, []) or [])]
        self._paused = False
        # П2 fail-safe: ящики, чью ПАУЗУ не удалось записать в БД (сбой store).
        # Пока мы живы — держим их вне отправки in-memory; успешная запись
        # паузы/резюма снимает метку.
        self._pause_write_failed: set[str] = set()

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

    @staticmethod
    def _accepts_now(fn) -> bool:
        """Есть ли у метода kwarg now — фейки в тестах могут жить по контрактной
        сигнатуре без него; ретраить по TypeError нельзя (риск дубля отправки)."""
        try:
            import inspect
            return "now" in inspect.signature(fn).parameters
        except (TypeError, ValueError):
            return False

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
            if mid in self._pause_write_failed:
                continue  # пауза гейта не легла в БД — держим in-memory
            try:
                st = self.store.get_mailbox_state(mid)
                if st is not None and bool(st.paused):
                    continue
            except Exception:  # noqa: BLE001
                # П2.3 fail-safe: не смогли прочитать паузу → ящик НЕ активен.
                # Раньше ящик попадал в отправку — паузнутый мог продолжить слать.
                logger.exception(
                    "get_mailbox_state failed mailbox=%s — исключаю из отправки", mid)
                continue
            ids.append(mid)
        return ids

    def _ensure_personalizer(self):
        if self._personalizer is None:
            try:
                from sender.personalize import Personalizer  # lazy, только если не внедрён
            except Exception as e:  # noqa: BLE001
                raise ConfigError(f"personalizer is not configured/available: {e}") from e
            self._personalizer = Personalizer(self.config, cards=self._cards)
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
            self._pause_write_failed.discard(mailbox_id)
        except Exception:  # noqa: BLE001
            logger.exception("set_mailbox_paused failed mailbox=%s paused=%s", mailbox_id, paused)
            if paused:
                # Гейт СКАЗАЛ паузить, а БД не записала — раньше следующий тик
                # видел paused=False и продолжал слать с трипнутого ящика.
                # Держим паузу in-memory до успешной записи/резюма.
                self._pause_write_failed.add(mailbox_id)

    # ------------------------------------------------------------------ #
    # lifecycle
    # ------------------------------------------------------------------ #
    def bootstrap(self) -> None:
        """init_schema + recover_stale + посев mailbox_state + fail-fast рендера."""
        self.store.init_schema()
        recovered = self.store.recover_stale(self.lease_ttl_sec)
        self._seed_mailbox_states()
        self._ensure_personalizer()  # кривая сборка падает на старте, а не в волне
        logger.info("bootstrap done: recovered_stale=%s", recovered)

    def _seed_mailbox_states(self) -> None:
        """Строки mailbox_state для ящиков конфига (если ещё нет).

        can_send_now живёт и без строки (лимит из рамп-кривой), а вот
        store.increment_sent после первой же отправки требует её — сеет
        composition root, ящик стартует с ramp_day=0 и лимитом дня 0 кривой."""
        try:
            from sender.dtos import MailboxState  # type: ignore
        except Exception:  # noqa: BLE001 - автономный режим без dtos
            try:
                from sender.store import MailboxState  # type: ignore
            except Exception:  # noqa: BLE001
                logger.exception("MailboxState недоступен — посев пропущен")
                return
        day_key = self._now().strftime("%Y-%m-%d")
        try:
            boxes = list(self.config.mailboxes())
        except Exception:  # noqa: BLE001
            logger.exception("config.mailboxes() failed")
            return
        for mb in boxes:
            try:
                if self.store.get_mailbox_state(mb.mailbox_id) is not None:
                    continue
                provider = getattr(mb, "provider", "") or ""
                # P2 №1: единый резолвер (пустая кривая больше не роняет сид)
                from sender.ramp import daily_send_limit
                limit = daily_send_limit(self.config, provider, 0)
                self.store.upsert_mailbox_state(MailboxState(
                    mailbox_id=mb.mailbox_id, provider=provider, day_key=day_key,
                    sent_today=0, sent_total=0, ramp_day=0, daily_limit=limit,
                    last_sent_at=None, paused=False, pause_reason=None))
            except Exception:  # noqa: BLE001
                logger.exception("seed mailbox_state failed %s", getattr(mb, "mailbox_id", mb))

    def _build_confirm_panel(self, recipient, campaign, rendered):
        """JSON инфо-панели для карточки подтверждения (best-effort).

        Источники: enrich.db (компания/контакты/сигналы; путь obzvon.enrich_db)
        + объединённая карточка company_card при активном индексе. Любой сбой →
        None: письмо всё равно ложится в очередь, карточка просто беднее —
        наполнение очереди важнее полноты панели."""
        try:
            from sender.infopanel import build_panel, load_enrich_lead
            inn = getattr(recipient, "inn", None)
            enrich_db = self.config.get("obzvon.enrich_db", "") or None
            ctx = load_enrich_lead(str(inn or ""), db_path=enrich_db,
                                   email=recipient.email)
            card = None
            if inn and self._cards is not None and getattr(self._cards, "active", False):
                try:
                    card = self._cards.card(inn)
                except Exception:  # noqa: BLE001
                    card = None
            return build_panel(
                inn=str(inn) if inn else None, email=recipient.email,
                letter_subject=rendered.subject, letter_body=rendered.body,
                company=ctx.get("company") or {}, emails=ctx.get("emails") or [],
                signals=ctx.get("signals") or [], store=self.store, card=card)
        except Exception:  # noqa: BLE001
            logger.exception("build_confirm_panel failed")
            return None

    def _division_queue_block(self, msg_in, campaign) -> "str | None":
        """§4 точка 1 (сборка очереди): причина не ставить письмо или None.

        Компания без направления (ИНН не из базы обзвона) — блок всегда;
        направление кампании (по сегменту) распознано и не совпало — блок.
        Гейт активен только при подключённом индексе обзвона; сбой проверки =
        блок (fail-safe, как у гейтов репутации П2.4)."""
        cards = self._cards
        if cards is None or not getattr(cards, "active", False):
            return None
        try:
            from sender.company_card import campaign_division
            rec = self.store.get_recipient(msg_in.recipient_id)
            comp_div = cards.division(getattr(rec, "inn", None)) if rec else None
            if comp_div is None:
                return "company_division_empty"
            camp_div = campaign_division(campaign)
            if camp_div is not None and camp_div != comp_div:
                return (f"campaign_division_mismatch:"
                        f"campaign={camp_div},company={comp_div}")
            return None
        except Exception:  # noqa: BLE001
            logger.exception("division queue gate failed")
            return "division_gate_error"

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
            # П2.4 fail-safe: гейты — защита репутации; их отказ не повод
            # лететь без защиты (раньше волна продолжалась как ни в чём не
            # бывало). Этот тик не планирует и не шлёт; паузы НЕ трогаем —
            # следующий тик с живыми гейтами продолжит сам.
            logger.exception(
                "gates.evaluate_all failed — тик без отправки (fail-safe)")
            global_tripped = True

        # гейт-трипы → Telegram (опционально; сбой уведомлений не роняет tick)
        if self._notifier is not None and gates_tripped:
            try:
                from sender.notify import notify_gate_trips  # ленивый опц. импорт
                notify_gate_trips(self._notifier, decisions, now=now)
            except Exception:  # noqa: BLE001
                logger.exception("notify_gate_trips failed")

        planned = 0
        sent = 0
        skipped = 0
        failed = 0
        warmup_sent = 0
        queued = 0   # положено в очередь подтверждений (confirm-режим)

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
                            div_reason = self._division_queue_block(
                                msg_in, campaign)
                            if div_reason is not None:
                                # §4 точка 1: письмо НЕ ставится в очередь
                                logger.warning(
                                    "division_gate_block(queue) campaign=%s "
                                    "recipient=%s: %s",
                                    cid, msg_in.recipient_id, div_reason)
                                continue
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
                                # §3 BASE-MERGE: очередь «дозаполнить данные»
                                reason = ("unfilled_fields:"
                                          + ",".join(rendered.unfilled_fields))
                                if hasattr(self.store, "mark_needs_data"):
                                    self.store.mark_needs_data(
                                        message.id, reason)
                                else:
                                    self.store.mark_failed(
                                        message.id, reason, retryable=False)
                                failed += 1
                                continue
                        except PersonalizationGateError as e:
                            # §3 BASE-MERGE: пустые обязательные поля (напр.
                            # {news_object}/{city} news-батча) — НЕ пустышка в
                            # отправку и НЕ могила failed, а очередь
                            # «дозаполнить данные» с причиной.
                            if hasattr(self.store, "mark_needs_data"):
                                self.store.mark_needs_data(message.id, str(e))
                            else:
                                self.store.mark_failed(
                                    message.id, str(e), retryable=False)
                            failed += 1
                            continue

                        # РЕЖИМ ПОДТВЕРЖДЕНИЯ: письмо отрендерено и валидно →
                        # вместо прямой отправки кладём в очередь подтверждений
                        # оператора (панель) и держим сообщение вне авто-отправки
                        # (status=pending_review). Реальный SMTP — только ручной
                        # approve. submit идемпотентен по (инн,email,кампания):
                        # повторный тик не сбрасывает уже одобренные.
                        if self._confirm is not None and self._confirm.mode() != "off":
                            try:
                                panel = self._build_confirm_panel(
                                    recipient, campaign, rendered)
                                self._confirm.submit(
                                    email=recipient.email,
                                    subject=rendered.subject, body=rendered.body,
                                    inn=getattr(recipient, "inn", None),
                                    campaign_id=message.campaign_id,
                                    recipient_id=message.recipient_id,
                                    message_id=message.id, panel=panel)
                                self.store.mark_pending_review(message.id)
                                queued += 1
                            except Exception:  # noqa: BLE001
                                # сбой постановки в очередь — НЕ шлём вслепую:
                                # оставляем 'sending', recover_stale вернёт в
                                # 'scheduled' к следующему тику (без потери письма).
                                logger.exception(
                                    "confirm.submit failed message_id=%s",
                                    message.id)
                                skipped += 1
                            continue

                        # pick_mailbox: часы тика передаём, если сендер их принимает
                        if self._accepts_now(self.sender.pick_mailbox):
                            mailbox_id = self.sender.pick_mailbox(recipient, campaign, now=now)
                        else:
                            mailbox_id = self.sender.pick_mailbox(recipient, campaign)
                        if not mailbox_id:
                            # некому слать СЕЙЧАС (пейсинг/лимит дня/пауза) — это
                            # не приговор письму. mark_skipped здесь терминально
                            # хоронил письмо; «оставить в 'sending' до recover_stale»
                            # (ревью №27, подтверждено) держало его мёртвым lease_ttl
                            # (15 мин) на ровном месте. Снимаем lease сразу — письмо
                            # снова claimable со следующего тика. Guard hasattr:
                            # мок-store юнитов без release_message → прежний путь
                            # через recover_stale (письмо всё равно не теряется).
                            logger.info("no mailbox available now message_id=%s", message.id)
                            if hasattr(self.store, "release_message"):
                                try:
                                    self.store.release_message(message.id)
                                except Exception:  # noqa: BLE001
                                    logger.exception(
                                        "release_message failed message_id=%s",
                                        message.id)
                            skipped += 1
                            continue

                        # sender.send уже внутри делает mark_sent/mark_failed/mark_skipped
                        try:
                            if self._accepts_now(self.sender.send):
                                result = self.sender.send(message, rendered, mailbox_id, now=now)
                            else:
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
            queued=queued,
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
