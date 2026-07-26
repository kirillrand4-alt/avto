"""Конвейер генерации ЧЕРНОВИКОВ ответа на входящие письма (ручная отправка).

Владелец: автоответчики/рассыльщики только СТАВЯТ письма в очередь; реально
отправляет оператор нажатием «Отправить». Этот модуль — недостающее звено:
входящий ответ клиента → черновик ответа (autoresponder.plan pilot +
render_reply + review_chain через провайдер) → confirm-очередь (kind='reply').
Оператор видит черновик с вердиктами ревью и жмёт «Отправить» → реальный SMTP
(sender.send_reply через ConfirmSend).

⛔ Здесь НИЧЕГО не отправляется — только кладётся в очередь. Отправка — за
оператором (ConfirmSend.approve в live-режиме). Тяжёлая часть (render_reply
шаблоны дешёвые, но review_chain ходит провайдером) — на боевом сервере через
gen_provider; в тестах caller передаётся моком.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

logger = logging.getLogger("sender.reply_pipeline")

# Классы, на которые робот ГОТОВИТ черновик ответа. unsub_request/not_interested/
# auto_reply отсекаются в imap_watcher._handle_reply ДО вызова конвейера
# (там своя обработка: suppression / молчим / игнор).
RESPONDABLE = frozenset({
    "interested", "neutral", "hot", "deferred", "redirect", "wrong_contact",
    "objection_tech", "objection_status_quo", "competitor_in_place",
})


class ReplyPipeline:
    """Готовит черновик ответа и кладёт в confirm-очередь. Сам не шлёт."""

    def __init__(self, config, store, confirm, *, caller=None, mode: str = "pilot"):
        self._config = config
        self._store = store
        self._confirm = confirm
        self._caller = caller          # LLM-caller для review_chain (None→провайдер)
        self._mode = mode              # pilot: всё в черновики (auto-send нет)

    def _enabled(self) -> bool:
        """Включён ли автоответчик. Тумблер панели — главный; он не выставлен —
        решает конфиг службы.

        Дефолт «включено» безопасен: конвейер НИЧЕГО не отправляет, он кладёт
        черновик в очередь подтверждений, и письмо уходит только когда оператор
        нажал «Отправить». Дефолт «выключено» стоил цепочки: на входящие ответы
        черновики просто не готовились, и в очереди ответов не появлялось."""
        try:
            v = self._store.get_setting("autoresponder_enabled", None)
        except Exception:  # noqa: BLE001 - стор без настроек/мок в тестах
            return True
        if v is not None:
            return bool(v)
        try:
            return bool(self._config.get("autoresponder.enabled", True))
        except Exception:  # noqa: BLE001 - конфиг без dotted get
            return True

    def draft_for_incoming(self, recipient, signal, ev) -> Optional[int]:
        """По входящему письму подготовить черновик ответа в очередь.

        Возвращает review_id или None (класс не отвечабельный / план пуст).
        """
        # ТУМБЛЕР ВЛАДЕЛЬЦА. Раньше автоответчик включался только строкой в
        # конфиге при СТАРТЕ службы — выключить его из панели было нельзя, а на
        # входящие он продолжал готовить черновики. Теперь состояние живёт в
        # panel_settings и проверяется на КАЖДОМ письме: выключил — и с этой
        # секунды новых черновиков нет, рестарт не нужен.
        if not self._enabled():
            return None

        kind = getattr(signal, "kind", None)
        if kind not in RESPONDABLE:
            return None

        from sender.autoresponder import plan, render_reply

        # suppressed=True вычёркивает reply_* (отписавшемуся не готовим ответ)
        suppressed = self._is_suppressed(recipient)
        actions = plan(signal, mode=self._mode, suppressed=suppressed)
        if not any(a.kind in ("reply_draft", "reply_auto") for a in actions):
            return None

        ctx = self._render_ctx(recipient, signal)
        subject, body = render_reply(kind, ctx)

        review = self._review(subject, body, ev, kind)
        panel = self._panel(recipient, signal, ev, review)

        res = self._confirm.submit_reply(
            reply_to=recipient.email, subject=review["subject"],
            body=review["body"], in_reply_to=getattr(ev, "rfc_message_id", None),
            thread_id=getattr(ev, "thread_id", None),
            recipient_id=recipient.id, inn=recipient.inn, panel=panel)
        logger.info("reply draft %s для %s (%s)", res.status, recipient.email, kind)
        return res.review_id

    # -- внутреннее -------------------------------------------------------- #

    def _is_suppressed(self, recipient) -> bool:
        try:
            from sender.suppression import Suppression
            return Suppression(self._store).is_suppressed(recipient) is not None
        except Exception:  # noqa: BLE001 - сомнение = как не suppressed (черновик
            return False   # всё равно пройдёт заслон submit_reply)

    def _render_ctx(self, recipient, signal) -> dict[str, Any]:
        return {
            "first_name": _first_word(getattr(recipient, "contact_name", "")),
            "company": getattr(recipient, "company_name", "") or "",
            "manager": "Менеджер направления",
            "new_contact": getattr(signal, "redirect_hint", None),
            "deferred_hint": getattr(signal, "deferred_hint", None),
        }

    def _review(self, subject: str, body: str, ev, kind: str) -> dict:
        """Прогон ревью-конвейера (провайдер). Сбой → отдаём как есть с
        пометкой (черновик всё равно смотрит человек)."""
        try:
            from sender.review_chain import review_chain
            result = review_chain(
                subject, body, incoming=getattr(ev, "snippet", "") or "",
                reply_kind=kind, caller=self._caller)
            return {
                "subject": result.subject, "body": result.body,
                "decision": result.decision,
                "escalate_reason": result.escalate_reason,
                "qa_problems": list(result.qa_problems),
                "iterations": result.iterations,
                "verdicts": {
                    name: {"verdict": v.verdict, "problems": list(v.problems)}
                    for name, v in result.verdicts.items()
                },
            }
        except Exception as exc:  # noqa: BLE001
            logger.exception("review_chain упал — черновик без ревью")
            return {"subject": subject, "body": body, "decision": "FIX",
                    "escalate_reason": f"ревью недоступно: {exc}",
                    "qa_problems": [], "iterations": 0, "verdicts": {}}

    def _panel(self, recipient, signal, ev, review: dict) -> dict:
        """Инфо-панель ответа: входящее, классификация, вердикты ревью."""
        hdrs = getattr(ev, "raw_headers", None) or {}
        return {
            "kind": "reply",
            # ветка диалога: с какого ящика клиент получил письмо и вся цепочка
            # References — иначе наш ответ придёт отдельным письмом (правка 26.07)
            "mailbox_id": getattr(ev, "mailbox_id", None),
            "references": hdrs.get("References", ""),
            "incoming": {
                "from": getattr(ev, "from_addr", "") or recipient.email,
                "snippet": getattr(ev, "snippet", "") or "",
                "classified": getattr(signal, "kind", ""),
                "phone": getattr(signal, "phone", None),
            },
            "company": {
                "name": getattr(recipient, "company_name", "") or "",
                "inn": getattr(recipient, "inn", None),
            },
            "review": {
                "decision": review["decision"],
                "escalate_reason": review["escalate_reason"],
                "qa_problems": review["qa_problems"],
                "verdicts": review["verdicts"],
            },
            "actions": {"hotkeys": {"Enter": "approve", "E": "edit",
                                    "S": "skip", "X": "stoplist"},
                        "confirm_hold": review["decision"] != "SEND"},
        }


def _first_word(name: Optional[str]) -> str:
    parts = (name or "").split()
    return parts[0] if parts else ""
