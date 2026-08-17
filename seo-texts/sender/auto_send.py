# -*- coding: utf-8 -*-
"""Автоотправка ОДОБРЕННЫХ писем — кнопка «в автоотправку» (владелец 06.08).

Зачем отдельный цикл: боевой сервер крутит только веб-панель (FastAPI),
оркестратор `python -m sender run` там не запущен. Даже если бы он был
запущен, в confirm-режиме он возвращает КАЖДОЕ claimed-письмо обратно в
очередь подтверждений — автоматической отправки одобренных не существовало
в принципе. Этот цикл закрывает ровно эту дыру и НИЧЕГО больше:

  * берёт только письма 'scheduled' с наступившим сроком, у которых
    ПОСЛЕДНИЙ confirm_review = approved/edited (то есть оператор нажал
    «в автоотправку» — каждое письмо прошло через решение человека);
  * текст — из review (правка оператора приоритетнее), НЕ из шаблона шага:
    у ai-кампаний шаблон '{subject}' и рендер уронил бы письмо;
  * час отправки — окно В ЗОНЕ ПОЛУЧАТЕЛЯ (владелец 06.08: «где компания
    зарегистрирована — то и считаем временем получателя»); вне окна письмо
    переносится на ближайший слот, а не шлётся ночью;
  * дневные лимиты/пейсинг/паузы ящиков — штатный pick_mailbox;
    юр-гейты (отписка, жалоба, направление) — внутри sender.send.

⛔ Холд: цикл СПИТ, пока в panel_settings нет auto_send_enabled=true.
Включает его ТОЛЬКО нажатие кнопки владельцем в панели (или явный POST
/auto-send). Выключение — тем же тумблером в любой момент.
"""
from __future__ import annotations

import logging
import threading
from datetime import datetime, time as dtime, timedelta, timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)

ENABLED_KEY = "auto_send_enabled"


def _zone(name: Optional[str]):
    try:
        from zoneinfo import ZoneInfo
        return ZoneInfo(name) if name else timezone.utc
    except Exception:  # noqa: BLE001 - битая зона -> UTC (хуже час, чем падение)
        return timezone.utc


def _hhmm(s: Optional[str], fallback: dtime) -> dtime:
    try:
        h, m = str(s).split(":")
        return dtime(int(h), int(m))
    except Exception:  # noqa: BLE001
        return fallback


def window_from(store: Any, config: Any) -> dict:
    """Окно отправки: override панели (panel_settings.sending_window)
    приоритетнее конфига — тот же порядок, что в sender._within_window."""
    try:
        ov = store.get_setting("sending_window")
    except Exception:  # noqa: BLE001
        ov = None
    if isinstance(ov, dict) and ov.get("days"):
        return {"days": [int(d) for d in ov.get("days") or []],
                "start": ov.get("start") or "09:00",
                "end": ov.get("end") or "18:00",
                "tz": ov.get("tz") or "Europe/Moscow",
                "by_recipient_tz": bool(ov.get("by_recipient_tz"))}
    try:
        w = config.sending_window()
        return {"days": list(w.days), "start": w.start, "end": w.end,
                "tz": w.tz, "by_recipient_tz": False}
    except Exception:  # noqa: BLE001 - фейк-конфиг тестов
        return {"days": [1, 2, 3, 4, 5], "start": "09:00", "end": "18:00",
                "tz": "Europe/Moscow", "by_recipient_tz": False}


def recipient_tz_name(win: dict, recipient: Any) -> Optional[str]:
    """Зона, в которой считается час письма ЭТОМУ получателю."""
    if win.get("by_recipient_tz"):
        tz = getattr(recipient, "tz", None)
        if tz is None and isinstance(recipient, dict):
            tz = recipient.get("tz")
        if tz:
            return str(tz)
    return str(win.get("tz") or "Europe/Moscow")


def within_window_now(win: dict, tz_name: Optional[str],
                      now: datetime) -> bool:
    """Сейчас — рабочий час окна в данной зоне? (праздники смотрит sender)."""
    local = now.astimezone(_zone(tz_name))
    days = {int(d) for d in (win.get("days") or [])} or {1, 2, 3, 4, 5}
    if local.isoweekday() not in days:
        return False
    start = _hhmm(win.get("start"), dtime(9, 0))
    end = _hhmm(win.get("end"), dtime(18, 0))
    return start <= local.time() <= end


def next_slot(win: dict, tz_name: Optional[str], now: datetime) -> datetime:
    """Ближайший момент окна в данной зоне (UTC, aware).

    Сейчас в окне → now (слать можно сразу). Иначе — начало окна сегодня
    (если ещё впереди) или ближайшего разрешённого дня. Это «не раньше чем»:
    дисциплину часа при by_recipient_tz несёт именно scheduled_at, воротник
    _within_window час не проверяет.
    """
    tz = _zone(tz_name)
    days = {int(d) for d in (win.get("days") or [])} or {1, 2, 3, 4, 5}
    start = _hhmm(win.get("start"), dtime(9, 0))
    end = _hhmm(win.get("end"), dtime(18, 0))
    local = now.astimezone(tz)
    if local.isoweekday() in days and start <= local.time() <= end:
        return now
    day = local.date()
    if local.isoweekday() not in days or local.time() > end:
        day += timedelta(days=1)
        while datetime.combine(day, start).isoweekday() not in days:
            day += timedelta(days=1)
    return datetime.combine(day, start, tzinfo=tz).astimezone(timezone.utc)


class AutoSendLoop:
    """Фоновый цикл панели: одобренные+созревшие письма → SMTP.

    live_sender — БОЕВОЙ Sender (dry_run=False), тот же, каким панель шлёт
    ручные approve (wiring: confirm.live_send=true). Панельный deps.sender
    dry-run и для этого не годится. Нет живого сендера → цикл честно спит.
    """

    def __init__(self, *, store: Any, config: Any, live_sender: Any,
                 interval_sec: int = 60, batch: int = 10):
        self.store = store
        self.config = config
        self.sender = live_sender
        self.interval = max(10, int(interval_sec))
        self.batch = max(1, int(batch))
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self.last_result: dict = {}

    # -- состояние ---------------------------------------------------------- #

    def enabled(self) -> bool:
        try:
            return bool(self.store.get_setting(ENABLED_KEY, False))
        except Exception:  # noqa: BLE001
            return False

    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    # -- один проход (тестируемое ядро) ------------------------------------- #

    def tick(self, *, now: Optional[datetime] = None) -> dict:
        out = {"sent": 0, "released": 0, "skipped": 0, "failed": 0}
        if self.sender is None or not self.enabled():
            return out
        now = now or datetime.now(timezone.utc)
        win = window_from(self.store, self.config)
        try:
            claimed = self.store.claim_approved_due(now=now, limit=self.batch)
        except Exception:  # noqa: BLE001
            logger.exception("auto_send: claim_approved_due упал")
            return out
        for m in claimed:
            try:
                self._send_one(m, win, now, out)
            except Exception:  # noqa: BLE001 - одно письмо не роняет цикл
                logger.exception("auto_send: письмо message_id=%s", m.id)
                try:
                    self.store.mark_failed(
                        m.id, "auto_send:unexpected", retryable=True)
                except Exception:  # noqa: BLE001
                    pass
                out["failed"] += 1
        self.last_result = dict(out, at=now.isoformat())
        return out

    def _send_one(self, m: Any, win: dict, now: datetime, out: dict) -> None:
        review = self.store.confirm_review_for_message(m.id)
        recipient = self.store.get_recipient(m.recipient_id)
        campaign = self.store.get_campaign(m.campaign_id)
        if not review or not recipient or not campaign:
            self.store.mark_skipped(m.id, "auto_send:missing_data")
            out["skipped"] += 1
            return
        tz_name = recipient_tz_name(win, recipient)
        if not within_window_now(win, tz_name, now):
            # не час получателя: вернуть в scheduled и подвинуть на слот —
            # иначе цикл каждую минуту зря вертел бы это письмо
            self.store.release_message(m.id)
            self.store.reschedule_message(m.id, next_slot(win, tz_name, now))
            out["released"] += 1
            return
        subject = review.get("edited_subject") or review.get("subject") or ""
        body = review.get("edited_body") or review.get("body") or ""
        if not subject.strip() or not body.strip():
            self.store.mark_skipped(m.id, "auto_send:empty_text")
            out["skipped"] += 1
            return
        from sender.dtos import RenderedMessage
        rendered = RenderedMessage(subject=subject, body=body)
        # message=m: подбор обязан знать направление ПИСЬМА, иначе он берёт
        # ящик по компании и компрессорное письмо уходит с адреса Meyer.
        mailbox_id = self.sender.pick_mailbox(recipient, campaign, now=now,
                                              message=m)
        if not mailbox_id:
            # лимит дня/пейсинг/праздник — не приговор: письмо ждёт следующего
            # тика в 'scheduled' (как ревью №27 в оркестраторе)
            self.store.release_message(m.id)
            out["released"] += 1
            return
        from sender.errors import (GateTrippedError, RateLimitExceeded,
                                   SuppressedError, TransientError)
        # адрес — из КАРТОЧКИ (оператор мог заменить), как в ручном approve
        try:
            res = self.sender.send(m, rendered, mailbox_id, now=now,
                                   to_email=(review.get("email") or None))
        except SuppressedError:
            # sender уже mark_skipped с причиной (отписка/ответ/направление)
            out["skipped"] += 1
            return
        except (GateTrippedError, RateLimitExceeded, TransientError):
            # временный заслон (гейт/лимит/молодой домен/сеть): письмо не
            # виновато — вернуть в 'scheduled', попробуем следующим тиком
            self.store.release_message(m.id)
            out["released"] += 1
            return
        if getattr(res, "ok", False):
            out["sent"] += 1
        else:
            # sender сам сделал mark_failed/mark_skipped с причиной
            out["failed" if getattr(res, "error", None) else "skipped"] += 1

    # -- фоновый запуск ------------------------------------------------------ #

    def start(self) -> None:
        if self.running():
            return
        self._stop.clear()

        def _run() -> None:
            logger.info("auto_send: цикл запущен (interval=%ss)", self.interval)
            while not self._stop.wait(self.interval):
                try:
                    r = self.tick()
                    if any(r.values()):
                        logger.info("auto_send: %s", r)
                except Exception:  # noqa: BLE001
                    logger.exception("auto_send: tick упал")

        self._thread = threading.Thread(
            target=_run, name="auto-send", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
