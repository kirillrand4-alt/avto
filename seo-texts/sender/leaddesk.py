"""Lead-desk: очередь тёплых лидов для продажников (BUILD-NEW, Фаза 2.1).

Эпицентр веб-панели (дыры p1·p2·p7 из SITE-DESIGN). ``push_warm_lead`` движка
раньше только выбрасывал лид в Bitrix; здесь — своя очередь с назначением,
взятием в работу через оптимистичную блокировку (никакого двойного захвата
двумя менеджерами), переходами статуса и SLA-дедлайнами.

Реализует протокол ``ReplyDeskSink`` (``push_warm_lead``), поэтому подключается
в ``ImapWatcher`` вместо/поверх ``BitrixSink``: входящий тёплый ответ → лид в
очереди, опционально дальше в Bitrix.

Только stdlib. Единственный писатель в БД — ``store``; leaddesk оркеструет
вызовы его методов (create_lead / update_lead_cas / list_leads).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from sender.errors import SenderError, ValidationError  # noqa: E402

logger = logging.getLogger("sender.leaddesk")


# Допустимые переходы статуса лида. Взятие/квалификация только вперёд;
# закрытие — из любого рабочего состояния.
_TRANSITIONS: dict[str, set[str]] = {
    "new": {"assigned", "taken", "closed"},
    "assigned": {"taken", "new", "closed"},
    "taken": {"qualified", "unqualified", "closed"},
    "qualified": {"closed"},
    "unqualified": {"closed"},
    "closed": set(),
}
_VALID_STATUSES = set(_TRANSITIONS)


@dataclass(frozen=True)
class LeadConflict(Exception):
    """Оптимистичная блокировка: лид изменён другим менеджером (устаревшая версия)."""
    lead_id: int
    message: str = "lead was modified concurrently"


class LeadDesk:
    """Очередь тёплых лидов поверх store. Реализует ReplyDeskSink."""

    def __init__(self, config: Any, store: Any, *, bitrix_sink: Any = None):
        self._config = config
        self._store = store
        self._bitrix = bitrix_sink  # опц. дальнейший проброс в Bitrix
        self._sla_hours = float(self._cfg("leaddesk.sla_hours", 4.0))

    def _cfg(self, key: str, default: Any) -> Any:
        try:
            val = self._config.get(key, default)
        except (AttributeError, TypeError):
            return default
        return default if val is None else val

    # ---- вход из imap_watcher (ReplyDeskSink) ---------------------------- #

    def push_warm_lead(self, recipient: Any, thread_id: str, snippet: str) -> Optional[int]:
        """Создать лид из входящего тёплого ответа. Идемпотентно по thread/email.

        ``snippet`` может нести префикс ``[hot, тел +7...] ...`` от imap_watcher —
        извлекаем reply_kind и телефон, остальное кладём в ``need``.
        """
        email = getattr(recipient, "email", None)
        if not email:
            return None
        reply_kind, phone, need = self._parse_snippet(snippet)
        dedup = f"lead:{thread_id}" if thread_id else f"lead:{email.strip().lower()}"
        sla_due = datetime.now(timezone.utc) + timedelta(hours=self._sla_hours)
        try:
            lead_id, created = self._store.create_lead(
                email=email,
                dedup_key=dedup,
                recipient_id=getattr(recipient, "id", None),
                thread_id=thread_id,
                company_name=getattr(recipient, "company_name", None),
                inn=getattr(recipient, "inn", None),
                reply_kind=reply_kind,
                phone=phone,
                need=need,
                sla_due_at=sla_due,
            )
        except Exception:  # noqa: BLE001 - lead-desk не должен ронять поллинг IMAP
            logger.exception("create_lead failed for %s", email)
            return None
        # проброс в Bitrix (если настроен) только для НОВЫХ лидов
        if created and self._bitrix is not None:
            try:
                bid = self._bitrix.push_warm_lead(recipient, thread_id, snippet)
                if bid:
                    self._store.update_lead_cas(
                        lead_id, expected_version=0, action="synced",
                        bitrix_lead_id=int(bid))
            except Exception:  # noqa: BLE001
                logger.exception("bitrix push after lead create failed")
        return lead_id

    @staticmethod
    def _parse_snippet(snippet: str) -> tuple[Optional[str], Optional[str], str]:
        """Разобрать '[hot, тел +79...] текст' → (reply_kind, phone, need)."""
        reply_kind = phone = None
        need = snippet or ""
        if snippet and snippet.startswith("["):
            close = snippet.find("]")
            if close != -1:
                tags = snippet[1:close]
                need = snippet[close + 1:].strip()
                for part in (t.strip() for t in tags.split(",")):
                    if part.startswith("тел "):
                        phone = part[4:].strip()
                    elif part and reply_kind is None:
                        reply_kind = part
        return reply_kind, phone, need

    # ---- действия менеджеров (CAS) --------------------------------------- #

    def take(self, lead_id: int, *, user_id: int) -> Any:
        """Взять лид в работу. Оптимистичная блокировка: если лид уже взят
        другим (версия сменилась) — LeadConflict. Двойной захват невозможен."""
        lead = self._require(lead_id)
        if lead.status not in ("new", "assigned"):
            raise ValidationError(f"lead {lead_id} not takeable in status {lead.status}")
        updated = self._store.update_lead_cas(
            lead_id, expected_version=lead.version, actor_user_id=user_id,
            action="taken", status="taken", assigned_to=user_id)
        if updated is None:
            raise LeadConflict(lead_id)
        return updated

    def assign(self, lead_id: int, *, manager_id: int, actor_user_id: Optional[int] = None) -> Any:
        """Назначить лид менеджеру (не забирая в работу)."""
        lead = self._require(lead_id)
        self._check_transition(lead.status, "assigned")
        updated = self._store.update_lead_cas(
            lead_id, expected_version=lead.version, actor_user_id=actor_user_id,
            action="assigned", status="assigned", assigned_to=manager_id)
        if updated is None:
            raise LeadConflict(lead_id)
        return updated

    def set_status(self, lead_id: int, *, status: str, user_id: Optional[int] = None,
                   note: Optional[str] = None) -> Any:
        """Сменить статус лида с валидацией перехода."""
        if status not in _VALID_STATUSES:
            raise ValidationError(f"unknown lead status {status!r}")
        lead = self._require(lead_id)
        self._check_transition(lead.status, status)
        fields: dict[str, Any] = {"status": status}
        if note is not None:
            fields["need"] = note
        updated = self._store.update_lead_cas(
            lead_id, expected_version=lead.version, actor_user_id=user_id,
            action="status_changed", **fields)
        if updated is None:
            raise LeadConflict(lead_id)
        return updated

    @staticmethod
    def _check_transition(cur: str, target: str) -> None:
        if target not in _TRANSITIONS.get(cur, set()):
            raise ValidationError(f"illegal lead transition {cur} -> {target}")

    def _require(self, lead_id: int) -> Any:
        lead = self._store.get_lead(lead_id)
        if lead is None:
            raise ValidationError(f"lead {lead_id} not found")
        return lead

    # ---- чтение для панели ----------------------------------------------- #

    def queue(self, *, status=None, assigned_to=None, unassigned=False,
              reply_kind=None, limit: int = 100, offset: int = 0) -> list:
        return self._store.list_leads(
            status=status, assigned_to=assigned_to, unassigned=unassigned,
            reply_kind=reply_kind, limit=limit, offset=offset)

    def get(self, lead_id: int):
        return self._store.get_lead(lead_id)

    def history(self, lead_id: int) -> list:
        return self._store.list_lead_events(lead_id)

    def stats(self) -> dict:
        return self._store.lead_stats()
