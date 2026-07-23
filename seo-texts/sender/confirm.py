"""Режим «подтвердить отправку» (ENGINEER-TASKS-CONFIRM-SEND, Задача 1).

Активируемая опция калибровки: каждое сгенерированное письмо ложится в очередь
pending_review с JSON инфо-панели и уходит в отправочную очередь ТОЛЬКО после
ручного решения оператора.

Конфиг:
    confirm:
      mode: off | all | sample     # all = каждое письмо; sample = каждое N-е
      sample_every: 10

Решения: approved | edited (правка сохраняется С ДИФОМ — золотые пары для
дообучения промптов) | skipped (+причина) | stoplist (+причина: конкурент /
нерелевант / плохие данные / по запросу).

Инварианты:
  * durable (SQLite, store.confirm_*) — очередь и решения переживают рестарт;
  * идемпотентность по (ИНН, email, campaign_id) — повторный submit не плодит
    дублей, повторное решение не перерешивает;
  * заслоны на этапе ОЧЕРЕДИ и на этапе ПОДТВЕРЖДЕНИЯ (Задача 3): бессрочная
    отписка/suppression + повторный контакт <90 дней;
  * ОДИН бекенд для CLI и веб-панели (Задача 4) — оба зовут этот модуль.

⛔ ХОЛД: модуль никогда не шлёт SMTP. approved лишь переводит письмо в
messages.status='scheduled' — реальную отправку делает orchestrator, который
при холде не запускается.
"""

from __future__ import annotations

import difflib
from dataclasses import dataclass
from typing import Any, Optional

from sender.errors import SenderError, ValidationError

# Причины стоп-листа (ТЗ) → reason в suppression (VALID_REASONS).
STOPLIST_REASONS = {
    "конкурент": "competitor",
    "нерелевант": "manual",
    "плохие данные": "manual",
    "по запросу": "unsubscribe",   # адресат просил не писать — навсегда
}

RECENT_CONTACT_DAYS = 90


class ConfirmBlockedError(SenderError):
    """Approve невозможен: юр-заслон (suppression/90 дней) сработал на этапе
    подтверждения. Письмо остаётся pending — решает оператор (skip/stoplist)."""


@dataclass(frozen=True)
class SubmitResult:
    review_id: int
    created: bool
    status: str          # pending | skipped (авто-заслон очереди) | bypassed
    reason: str = ""


class ConfirmSend:
    """Очередь подтверждений поверх store. Все решения — через decide()."""

    def __init__(self, config, store, suppression=None):
        self._config = config
        self._store = store
        self._suppression = suppression

    # -- конфиг ------------------------------------------------------------ #

    def mode(self) -> str:
        try:
            m = str(self._config.get("confirm.mode", "off") or "off").lower()
        except Exception:  # noqa: BLE001 - фейк-конфиг без get
            m = "off"
        return m if m in ("off", "all", "sample") else "off"

    def sample_every(self) -> int:
        try:
            n = int(self._config.get("confirm.sample_every", 10) or 10)
        except Exception:  # noqa: BLE001
            n = 10
        return max(1, n)

    # -- заслоны (общие для очереди и подтверждения) ------------------------ #

    def _guard(self, *, inn: Optional[str], email: str) -> Optional[str]:
        """Причина блокировки или None. Проверяет suppression (отписка
        навсегда и пр.) и повторный контакт <90 дней (Задача 3)."""
        entry = self._suppression_hit(inn=inn, email=email)
        if entry is not None:
            return f"suppressed:{entry.reason}"
        last = self._recent_contact(inn=inn, email=email)
        if last is not None:
            return f"recent_contact<{RECENT_CONTACT_DAYS}d:{last.get('ts', '')[:10]}"
        return None

    def _suppression_hit(self, *, inn: Optional[str], email: str):
        if self._suppression is None:
            return None
        from types import SimpleNamespace
        probe = SimpleNamespace(email=email, domain=email.rsplit("@", 1)[-1],
                                inn=inn)
        try:
            return self._suppression.is_suppressed(probe)
        except Exception:  # noqa: BLE001 - fail-safe: сомнение = блок
            return type("E", (), {"reason": "suppression_check_failed"})()

    def _recent_contact(self, *, inn: Optional[str], email: str):
        from datetime import datetime, timedelta, timezone
        last = None
        try:
            last = self._store.last_contact(email=email, inn=inn)
        except Exception:  # noqa: BLE001 - нет таблицы у мок-store
            return None
        if not last:
            return None
        ts = str(last.get("ts") or "")
        try:
            then = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            if then.tzinfo is None:
                then = then.replace(tzinfo=timezone.utc)
        except ValueError:
            return last  # дата не парсится → консервативно считаем недавним
        if datetime.now(timezone.utc) - then < timedelta(days=RECENT_CONTACT_DAYS):
            return last
        return None

    # -- постановка в очередь ----------------------------------------------- #

    def submit(
        self, *, email: str, subject: str, body: str,
        inn: Optional[str] = None, campaign_id: Optional[int] = None,
        recipient_id: Optional[int] = None, message_id: Optional[int] = None,
        panel: Optional[dict] = None,
    ) -> SubmitResult:
        """Письмо на подтверждение. Поведение по confirm_mode:
        off → bypassed (вызывающий шлёт по старому пути); sample → каждое N-е
        в очередь, остальные bypassed; all → каждое в очередь.

        Заслон этапа очереди: suppression / контакт <90 дн — письмо ложится
        сразу как skipped с причиной (след для лога), в pending не попадает.
        """
        mode = self.mode()
        if mode == "off":
            return SubmitResult(review_id=0, created=False, status="bypassed")

        blocked = self._guard(inn=inn, email=email)
        if blocked:
            rid, created = self._store.confirm_submit(
                email=email, subject=subject, body=body, inn=inn,
                campaign_id=campaign_id, recipient_id=recipient_id,
                message_id=message_id, panel=panel,
                status="skipped", reason=f"auto:{blocked}",
            )
            return SubmitResult(rid, created, "skipped", blocked)

        if mode == "sample":
            # Детерминированный сэмпл: каждое N-е письмо кампании — в очередь.
            # Пропущенные тоже пишутся (status='bypassed'): это durable-счётчик
            # позиции И аудит-след «письмо шло мимо калибровки». Повторный
            # submit того же письма идемпотентен и позицию не сдвигает.
            existing = self._store.confirm_get_by_key(inn, email, campaign_id)
            if existing is not None:
                return SubmitResult(existing["id"], False, existing["status"],
                                    existing.get("reason") or "")
            idx = len(self._store.confirm_list(
                campaign_id=campaign_id, limit=1_000_000))
            if idx % self.sample_every() != 0:
                rid, created = self._store.confirm_submit(
                    email=email, subject=subject, body=body, inn=inn,
                    campaign_id=campaign_id, recipient_id=recipient_id,
                    message_id=message_id, panel=panel,
                    status="bypassed", reason="sample_pass",
                )
                return SubmitResult(rid, created, "bypassed", "sample_pass")

        rid, created = self._store.confirm_submit(
            email=email, subject=subject, body=body, inn=inn,
            campaign_id=campaign_id, recipient_id=recipient_id,
            message_id=message_id, panel=panel,
        )
        return SubmitResult(rid, created, "pending")

    # -- чтение ------------------------------------------------------------- #

    def pending(self, *, campaign_id: Optional[int] = None,
                limit: int = 50, offset: int = 0) -> list[dict]:
        return self._store.confirm_list(
            status="pending", campaign_id=campaign_id, limit=limit, offset=offset)

    def get(self, review_id: int) -> Optional[dict]:
        return self._store.confirm_get(review_id)

    def counts(self) -> dict:
        return self._store.confirm_counts()

    def golden_pairs(self, *, limit: int = 500) -> list[dict]:
        """Правки оператора с дифами — сырьё для калибровки промптов."""
        rows = self._store.confirm_list(status="edited", limit=limit)
        return [
            {"review_id": r["id"], "email": r["email"], "inn": r.get("inn"),
             "campaign_id": r.get("campaign_id"),
             "original_subject": r["subject"], "original_body": r["body"],
             "edited_subject": r.get("edited_subject") or r["subject"],
             "edited_body": r.get("edited_body") or r["body"],
             "diff": r.get("diff_text") or ""}
            for r in rows
        ]

    # -- решения ------------------------------------------------------------ #

    def approve(self, review_id: int, *, operator: str = "") -> bool:
        row = self._require_pending(review_id)
        # Заслон этапа ПОДТВЕРЖДЕНИЯ: между постановкой и решением адрес мог
        # отписаться / получить письмо другим путём.
        blocked = self._guard(inn=row.get("inn"), email=row["email"])
        if blocked:
            raise ConfirmBlockedError(
                f"отправка запрещена ({blocked}) — письмо остаётся на решении: "
                "скип или стоп-лист")
        return self._store.confirm_decide(
            review_id, status="approved", decided_by=operator)

    def edit(self, review_id: int, *, subject: Optional[str] = None,
             body: Optional[str] = None, operator: str = "") -> bool:
        """Правка оператора: сохраняем текст И unified-диф (золотая пара),
        письмо уходит в очередь с новым текстом."""
        row = self._require_pending(review_id)
        blocked = self._guard(inn=row.get("inn"), email=row["email"])
        if blocked:
            raise ConfirmBlockedError(
                f"отправка запрещена ({blocked}) — правка не выпускает письмо")
        new_subject = subject if subject is not None else row["subject"]
        new_body = body if body is not None else row["body"]
        if new_subject == row["subject"] and new_body == row["body"]:
            # Правка без изменений = обычный approve (диф пустой не храним).
            return self._store.confirm_decide(
                review_id, status="approved", decided_by=operator)
        diff = build_diff(row["subject"], row["body"], new_subject, new_body)
        return self._store.confirm_decide(
            review_id, status="edited", edited_subject=new_subject,
            edited_body=new_body, diff_text=diff, decided_by=operator)

    def skip(self, review_id: int, *, reason: str, operator: str = "") -> bool:
        if not (reason or "").strip():
            raise ValidationError("skip требует причину")
        self._require_pending(review_id)
        return self._store.confirm_decide(
            review_id, status="skipped", reason=reason.strip(),
            decided_by=operator)

    def regenerate(self, review_id: int, *, operator: str = "") -> dict:
        """Снять письмо с очереди на ПЕРЕГЕНЕРАЦИЮ (владелец 2026-07-23): текущий review
        уходит из pending (status='skipped', reason='regenerate'), вызывающий (api) генерит
        новое письмо и кладёт его submit-ом в КОНЕЦ очереди. Возврат: снятая строка (данные
        получателя для регенерации)."""
        row = self._require_pending(review_id)
        self._store.confirm_decide(
            review_id, status="skipped", reason="regenerate",
            decided_by=operator or "operator")
        return row

    def stoplist(self, review_id: int, *, reason: str, operator: str = "") -> bool:
        """Стоп-лист: причина обязательна и из фиксированного набора.
        Сначала suppression (юр-важнее; идемпотентно), потом решение — при
        падении между ними повторный вызов докатывает решение."""
        key = (reason or "").strip().lower()
        if key not in STOPLIST_REASONS:
            raise ValidationError(
                f"stoplist: причина из набора {sorted(STOPLIST_REASONS)}")
        row = self._require_pending(review_id)
        supp_reason = STOPLIST_REASONS[key]
        if self._suppression is not None:
            self._suppression.add_email(
                row["email"], supp_reason,
                source=f"confirm_stoplist:{key}:{operator or 'operator'}")
            if key == "конкурент" and row.get("inn"):
                try:
                    self._suppression.add_inn(
                        row["inn"], "competitor",
                        source=f"confirm_stoplist:{operator or 'operator'}")
                except ValidationError:
                    pass  # битый ИНН в данных — email-запись уже стоит
        return self._store.confirm_decide(
            review_id, status="stoplist", reason=key, decided_by=operator)

    # -- внутреннее --------------------------------------------------------- #

    def _require_pending(self, review_id: int) -> dict:
        row = self._store.confirm_get(review_id)
        if row is None:
            raise ValidationError(f"review {review_id} не найден")
        return row


def build_diff(old_subject: str, old_body: str,
               new_subject: str, new_body: str) -> str:
    """Unified-диф письма (тема + тело) — формат золотых пар."""
    old = f"Тема: {old_subject}\n\n{old_body}".splitlines(keepends=True)
    new = f"Тема: {new_subject}\n\n{new_body}".splitlines(keepends=True)
    return "".join(difflib.unified_diff(
        old, new, fromfile="original", tofile="edited", lineterm="\n"))
