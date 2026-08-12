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
import logging
from dataclasses import dataclass
from typing import Optional

from sender.errors import SenderError, ValidationError

# Ревью #48: logger использовался в _audit_force, но не был определён — при
# сбое записи аудита ручной force-обход падал NameError ВМЕСТО отправки.
logger = logging.getLogger("sender.confirm")

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


class ManualRecipientDisabled(ConfirmBlockedError):
    """Ручное добавление контакта выключено тумблером (мгновенный откат фичи
    без выкатки). Отдельный класс, чтобы транспорт отдал 403, а не 409: это
    не заслон по адресу, а выключенная возможность."""


@dataclass(frozen=True)
class SubmitResult:
    review_id: int
    created: bool
    status: str          # pending | skipped (авто-заслон очереди) | bypassed
    reason: str = ""


class ConfirmSend:
    """Очередь подтверждений поверх store. Все решения — через decide().

    sender: если задан (confirm.live_send=true в wiring), РУЧНОЕ решение
    approve/edit отправляет письмо НЕМЕДЛЕННО по боевому SMTP (оператор нажал
    «Отправить» → реально ушло). Если None — approve только переводит письмо в
    очередь (scheduled), как раньше. Автоматика (оркестратор/автоответчик)
    сюда не ходит — она лишь ставит письма в pending_review.
    """

    def __init__(self, config, store, suppression=None, sender=None,
                 cards=None, probe=None):
        self._config = config
        self._store = store
        self._suppression = suppression
        self._sender = sender
        # Кэш проверок адресов: заслон недоставимых на подтверждении. None —
        # заслон молчит (тесты, инструменты), отправку не ломает.
        self._probe = probe
        # Гейт направлений §4, точка 2 (экран подтверждения): CompanyCards
        self._cards = cards

    # -- гейт направлений (§4 точка 2) -------------------------------------- #

    def _allow_out_of_base(self) -> bool:
        """Тумблер владельца «слать по email вне базы» (дефолт ВЫКЛ). Приоритет:
        panel_settings['allow_out_of_base'] (тумблер из UI) → confirm.allow_out_of_base
        (конфиг) → False. ВЫКЛ = вне-базы блокируется на approve."""
        try:
            v = self._store.get_setting("allow_out_of_base", None)
            if v is not None:
                return bool(v)
        except Exception:  # noqa: BLE001 - store без get_setting (старый/мок)
            pass
        try:
            return bool(self._config.get("confirm.allow_out_of_base", False))
        except Exception:  # noqa: BLE001 - фейк-конфиг
            return False

    def _division_flags(self, *, inn, campaign_id) -> list:
        """Красные стоп-флаги направления для панели; [] если гейт неактивен/ок."""
        cards = self._cards
        if cards is None or not getattr(cards, "active", False):
            return []
        # решение владельца 25.07: направление сверяем по метке И по потребностям
        # компании («Все категории оборудования»), см. company_card.divisions
        allowed = None
        getter = getattr(cards, "divisions", None)
        if callable(getter):
            allowed = getter(inn)
        comp_div = cards.division(inn)
        if allowed is None and comp_div is not None:
            allowed = {p for p in str(comp_div).split("+") if p}
        if allowed is None and comp_div is None:      # ИНН вообще не из базы
            if self._allow_out_of_base():
                # тумблер ВКЛ: вне-базы разрешено — жёлтое предупреждение, НЕ блок
                return [{"code": "out_of_base_allowed", "severity": "yellow",
                         "label": "ИНН вне базы обзвона — отправка РАЗРЕШЕНА "
                                  "тумблером «слать вне базы» (проверьте адрес)"}]
            return [{"code": "division_unknown", "severity": "red",
                     "label": "направление НЕ ОПРЕДЕЛЕНО (ИНН не из базы "
                              "обзвона) — отправка запрещена; включите тумблер "
                              "«слать по email вне базы», если это осознанно"}]
        if not allowed:                               # в базе, но ни метки, ни нужд
            return [{"code": "division_unknown", "severity": "red",
                     "label": "направление НЕ ОПРЕДЕЛЕНО: у компании в базе нет "
                              "ни метки направления, ни категорий оборудования"}]
        camp_div = None
        if campaign_id:
            try:
                from sender.company_card import campaign_division
                camp = self._store.get_campaign(campaign_id)
                camp_div = campaign_division(camp) if camp else None
            except Exception:  # noqa: BLE001 - нет кампании у мок-store
                camp_div = None
        if camp_div is not None and allowed and camp_div not in allowed:
            return [{"code": "division_mismatch", "severity": "red",
                     "label": f"НАПРАВЛЕНИЯ НЕ СОВПАДАЮТ: кампания {camp_div}, "
                              f"компании подходит {'+'.join(sorted(allowed))} "
                              "(метка базы + потребности) — отправка заблокирована"}]
        return []

    def _division_blocked(self, row) -> "str | None":
        """Причина блока approve/edit по направлениям или None (§4: не
        «доп-подтверждение», а именно блок кнопки). Жёлтые флаги (вне-базы при
        ВКЛ-тумблере) — предупреждение, НЕ блок."""
        flags = [f for f in self._division_flags(
            inn=row.get("inn"), campaign_id=row.get("campaign_id"))
            if f.get("severity") == "red"]
        if flags:
            return flags[0]["label"]
        return None

    @property
    def live(self) -> bool:
        """True — approve/edit шлют вживую по SMTP; False — кладут в очередь."""
        return self._sender is not None

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
        навсегда и пр.), повторный контакт <90 дней (Задача 3) и заведомо
        недоставимый адрес."""
        entry = self._suppression_hit(inn=inn, email=email)
        if entry is not None:
            return f"suppressed:{entry.reason}"
        мёртв = self._nedostavimyy(email)
        if мёртв:
            return мёртв
        last = self._recent_contact(inn=inn, email=email)
        if last is not None:
            return f"recent_contact<{RECENT_CONTACT_DAYS}d:{last.get('ts', '')[:10]}"
        return None

    def _nedostavimyy(self, email: str) -> Optional[str]:
        """Заведомо недоставимый адрес: не пускаем к отправке.

        Владелец 12.08: «нам бы домены свои не сжечь, надо страховаться сразу».
        Отбивка бьёт по репутации домена отправки, а два случая известны
        заранее: сервер прямо сказал «такого пользователя нет», и у домена нет
        почтового сервера. До этой правки заслон подтверждения смотрел только
        отписку и 90-дневную гигиену: мёртвый адрес спасало лишь то, что проба
        попутно кладёт его в стоп-лист, — но письмо, одобренное раньше приёма
        вердиктов, уходило.

        Что здесь НЕ делается: живая SMTP-проба. Она разговаривает с чужим
        почтовым сервером, и делать это с боевого адреса рассылки дорого —
        поэтому собственная проба панели выключена, а работает работник на
        отдельной машине. Здесь только чтение готового вердикта и, если его
        нет, проверка MX домена — DNS-запрос репутацию не тратит.
        """
        адрес = str(email or "").strip().lower()
        if "@" not in адрес:
            return None
        try:
            from sender.addr_probe import НЕТ_MX, НЕТ_ЯЩИКА
        except Exception:  # noqa: BLE001 - без модуля пробы заслон не работает
            return None
        проба = getattr(self, "_probe", None)
        if проба is not None:
            try:
                запись = проба.cached(адрес) or {}
            except Exception:  # noqa: BLE001
                запись = {}
            в = str(запись.get("verdict") or "")
            if в == НЕТ_ЯЩИКА:
                return f"адрес не существует: {str(запись.get('answer'))[:60]}"
            if в == НЕТ_MX:
                return f"у домена нет почтового сервера: {адрес.rsplit('@', 1)[-1]}"
            if в:
                return None            # вердикт есть и он не смертельный
            # Вердикта нет вовсе — проверяем хотя бы домен. Это дёшево и ловит
            # главный источник гарантированных отбивок: опечатки в домене.
            try:
                приговор, почему = проба._net_mx_dvazhdy(адрес.rsplit("@", 1)[-1])
                if приговор:
                    return f"у домена нет почтового сервера ({почему[:50]})"
            except Exception:  # noqa: BLE001 - сомнение толкуем в пользу отправки
                return None
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

        # §4 точка 2: несовпадение/пустое направление — красный стоп-флаг в
        # панели карточки (кнопка «Отправить» на бэке блокируется в approve).
        div_flags = self._division_flags(inn=inn, campaign_id=campaign_id)
        if div_flags:
            panel = dict(panel or {})
            panel["stop_flags"] = list(panel.get("stop_flags") or []) + div_flags
            actions = dict(panel.get("actions") or {})
            actions["confirm_hold"] = True
            panel["actions"] = actions

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
        # Ревью №12: карточка, зависшая в 'sending_live' после рестарта панели
        # посреди approve, исчезала из очереди навсегда. Освобождаем такие
        # перед показом очереди — оператор увидит письмо снова и повторит.
        rec = getattr(self._store, "recover_stale_reviews", None)
        if callable(rec):
            try:
                rec()
            except Exception:  # noqa: BLE001 - восстановление не должно ронять очередь
                pass
        # временная шторка (panel_settings 'confirm.hide_before'): пока идёт
        # массовая перегенерация, оператор видит только уже пересобранные
        # письма; готовые всплывают по мере обновления updated_at. Снять
        # шторку = удалить настройку (set_setting(..., None)).
        скрыть_до = None
        try:
            скрыть_до = self._store.get_setting("confirm.hide_before", None)
        except Exception:  # noqa: BLE001 - нет настроек (старые тесты) → без шторки
            pass
        return self._store.confirm_list(
            status="pending", campaign_id=campaign_id, limit=limit, offset=offset,
            updated_after=скрыть_до)

    def get(self, review_id: int) -> Optional[dict]:
        return self._store.confirm_get(review_id)

    def counts(self) -> dict:
        return self._store.confirm_counts()

    def set_recipient_email(self, review_id: int, email: str, *,
                            operator: str = "", actor_user_id=None) -> dict:
        """Сменить адрес получателя на другой контакт ЭТОЙ компании.

        Разрешён только адрес из контактов карточки (panel.emails) — чтобы
        оператор не вписал произвольный/чужой адрес. Меняет email + dedup;
        пишет audit recipient_changed (старый→новый). Гейты
        (suppression/division/mx) сработают при отправке по новому адресу."""
        row = self._require_pending(review_id)
        target = (email or "").strip().lower()
        allowed = {(e.get("email") or "").strip().lower()
                   for e in ((row.get("panel") or {}).get("emails") or [])}
        # panel.company_full.contacts.emails — второй источник (полная карточка)
        cf = (row.get("panel") or {}).get("company_full") or {}
        for e in (cf.get("contacts") or {}).get("emails", []) or []:
            allowed.add((e.get("email") or "").strip().lower())
        if allowed and target not in allowed:
            raise ConfirmBlockedError(
                f"адрес {target} не из контактов компании — выберите из списка")
        old = row.get("email")
        updated = self._store.confirm_change_email(review_id, target)
        try:
            self._store.append_audit(
                action="recipient_changed", actor_user_id=actor_user_id,
                entity_type="confirm_review", entity_id=review_id,
                detail={"old": old, "new": target, "operator": operator})
        except Exception:  # noqa: BLE001 - audit не критичен
            pass
        return updated

    # -- ручное добавление контакта компании -------------------------------- #

    def _manual_recipient_allowed(self) -> bool:
        """Тумблер «оператор может вписать новый адрес» (дефолт ВКЛ).
        Приоритет тот же, что у allow_out_of_base: panel_settings (из UI) →
        confirm.allow_manual_recipient (config.yaml) → True. Нужен, чтобы
        фичу можно было погасить рестартом службы, без выкатки пакета."""
        try:
            v = self._store.get_setting("allow_manual_recipient", None)
            if v is not None:
                return bool(v)
        except Exception:  # noqa: BLE001 - store без get_setting (старый/мок)
            pass
        try:
            return bool(self._config.get("confirm.allow_manual_recipient", True))
        except Exception:  # noqa: BLE001 - фейк-конфиг
            return True

    def _base_recipient(self, row: dict) -> dict:
        """Реквизиты компании исходного получателя карточки (тем же путём, что
        _send_live_inner: message_id → messages → recipients). Пусто, если
        карточка без письма (ответ в тред) или строка не найдена."""
        mid = row.get("message_id")
        if mid is None:
            return {}
        try:
            message = self._store.get_message(mid)
            rec = (self._store.get_recipient(message.recipient_id)
                   if message is not None else None)
        except Exception:  # noqa: BLE001 - мок-store в юнитах
            return {}
        if rec is None:
            return {}
        return {k: getattr(rec, k, None) for k in
                ("company_name", "okved", "segment", "region", "tz", "bitrix_id")}

    def add_recipient_email(self, review_id: int, email: str, *,
                            note: Optional[str] = None, operator: str = "",
                            actor_user_id=None) -> dict:
        """Добавить контакт, которого нет в карточке, привязать его к ИНН этой
        карточки (база обзвона) и сразу сделать получателем письма.

        Зачем отдельная ручка: старая (set_recipient_email) намеренно закрыта
        allow-листом контактов карточки — «чтобы оператор не вписал
        произвольный/чужой адрес». Решение владельца остаётся в силе: свободный
        ввод идёт ДРУГИМ путём, где адрес сначала проверяется (формат,
        стоп-лист, чужой ИНН) и заводится в базу получателей под ИНН карточки,
        и только потом попадает в её allow-лист. Ослаблять старую ручку не
        требуется — она отрабатывает штатно, вместе с дедупом очереди.

        Область — контакт ТОГО ЖЕ предприятия. Адрес, уже закреплённый в
        recipients за другим ИНН, отклоняется: upsert_recipient идёт
        ON CONFLICT(email) DO UPDATE и молча перезаписал бы чужую привязку.
        """
        if not self._manual_recipient_allowed():
            raise ManualRecipientDisabled(
                "ручное добавление адреса выключено настройкой "
                "confirm.allow_manual_recipient")
        row = self._require_pending(review_id)
        status = (row.get("status") or "").strip()
        if status != "pending":
            # Проверяем ДО записи в базу получателей: иначе на карточке,
            # которую уже отправили, мы бы завели контакт и только потом
            # упёрлись в отказ смены адреса.
            raise ValidationError(
                f"карточка {review_id} не в статусе pending (сейчас {status})")

        # (а) формат адреса — тем же нормализатором, что импортёр базы
        from sender.importer import _normalize_email
        target = _normalize_email(email or "")
        if not target:
            raise ValidationError(f"некорректный адрес: {email!r}")

        inn = "".join(ch for ch in str(row.get("inn") or "") if ch.isdigit())
        if not inn:
            # Объём, согласованный владельцем, — «с привязкой к ИНН из базы
            # обзвона». Без ИНН привязывать не к чему, а проверка «адрес чужой
            # компании» перестаёт работать: отказываем явно.
            raise ValidationError(
                "у карточки нет ИНН — новый адрес не к чему привязать; "
                "верный путь: скип карточки и перегенерация под нужную компанию")

        # (б) стоп-лист по НОВОМУ адресу/домену/ИНН — тем же вызовом, что approve
        hit = self._suppression_hit(inn=inn, email=target)
        if hit is not None:
            raise ConfirmBlockedError(
                f"адрес {target} в стоп-листе ({getattr(hit, 'reason', '?')}) "
                "— добавить нельзя")

        # (в) адрес не должен принадлежать ДРУГОЙ компании
        exist = None
        finder = getattr(self._store, "find_recipient_by_email", None)
        if callable(finder):
            exist = finder(target)
        if exist and (exist.get("inn") or "").strip() and exist["inn"] != inn:
            raise ConfirmBlockedError(
                f"адрес {target} уже закреплён за ИНН {exist['inn']}, "
                f"карточка — ИНН {inn}: адрес чужой компании добавлять нельзя")

        created = False
        if not exist:
            from sender.dtos import RecipientIn
            base = self._base_recipient(row)
            company = (row.get("panel") or {}).get("company") or {}
            self._store.upsert_recipient(RecipientIn(
                email=target,
                domain=target.split("@", 1)[1],
                inn=inn,
                company_name=base.get("company_name") or company.get("name"),
                okved=base.get("okved") or company.get("okved"),
                segment=base.get("segment"),
                contact_name=None,
                source="panel_manual",
                region=base.get("region"),
                tz=base.get("tz"),
            ))
            created = True

        # (г) аудит — ДО подмены и БЕЗ глушения: здесь меняется база
        # получателей, а не только карточка. Если след не записался, операцию
        # доводить нельзя — иначе на вопрос «откуда в базе этот адрес» ответа
        # не будет.
        self._store.append_audit(
            action="recipient_added", actor_user_id=actor_user_id,
            entity_type="confirm_review", entity_id=review_id,
            detail={"email": target, "inn": inn, "created_recipient": created,
                    "operator": operator, "note": note})

        # (д) адрес — в контакты карточки: дальше он проходит allow-лист
        # штатно и виден оператору в выпадающем списке «кому».
        panel = dict(row.get("panel") or {})
        emails = list(panel.get("emails") or [])
        if not any((e.get("email") or "").strip().lower() == target
                   for e in emails):
            from datetime import datetime, timezone
            emails.append({"email": target, "role": "добавлен оператором",
                           "person": None, "mx_ok": None, "source": "оператор",
                           "source_url": None, "added_by": operator,
                           "added_at": datetime.now(timezone.utc).isoformat()})
            panel["emails"] = emails
            self._store.confirm_set_panel(review_id, panel)

        # (е) дальше — штатная ручка: dedup_key, статус pending, коллизия очереди
        review = self.set_recipient_email(review_id, target, operator=operator,
                                          actor_user_id=actor_user_id)
        return {"review": review, "created_recipient": created}

    def golden_pairs(self, *, limit: int = 500) -> list[dict]:
        """Правки оператора с дифами — сырьё для калибровки промптов.
        Выборка по факту правки, не по статусу: в live-режиме правленое
        письмо сразу 'sent', фильтр status='edited' терял боевые пары."""
        rows = self._store.confirm_golden(limit=limit)
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

    def approve(self, review_id: int, *, operator: str = "",
                force: bool = False, actor_user_id=None,
                division: Optional[str] = None) -> bool:
        """Оператор нажал «Отправить». В live-режиме (sender задан) письмо
        УХОДИТ НЕМЕДЛЕННО по боевому SMTP; иначе — в очередь (scheduled).

        Для kind='reply' (ответ клиенту) 90-дневный/recent-заслон НЕ применяем
        — клиент сам инициировал диалог; отписку/жалобу проверит send_reply.

        force=True — РУЧНОЙ обход заслонов по двойному подтверждению оператора
        (решение владельца 26.07: «при двойном подтверждении письмо должно
        уходить в любом случае»). Обход применяется только к письму, на котором
        оператор лично нажал подтверждение второй раз, и пишется в аудит с
        перечнем того, что обошли: след обязателен, потому что среди заслонов
        есть отписка и жалоба (ФЗ-38), а не только 90-дневная гигиена.
        """
        row = self._require_pending(review_id)
        if row.get("kind") != "reply":
            # Заслон этапа ПОДТВЕРЖДЕНИЯ для исходящих: между постановкой и
            # решением адрес мог отписаться / получить письмо другим путём.
            blocked = self._guard(inn=row.get("inn"), email=row["email"])
            # §4 точка 2: гейт направлений БЛОКИРУЕТ кнопку (не спрашивает).
            div_blocked = self._division_blocked(row)
            if (blocked or div_blocked) and force:
                self._audit_force(review_id, row, operator, actor_user_id,
                                  blocked, div_blocked)
            elif blocked:
                raise ConfirmBlockedError(
                    f"отправка запрещена ({blocked}) — письмо остаётся на "
                    "решении: скип или стоп-лист")
            elif div_blocked:
                raise ConfirmBlockedError(f"гейт направлений: {div_blocked}")
        if self._sender is not None:
            self._send_live(row, row["subject"], row["body"], operator,
                            force=force, prefer_division=division)
            return True
        return self._store.confirm_decide(
            review_id, status="approved", decided_by=operator)

    def _audit_force(self, review_id, row, operator, actor_user_id,
                     blocked, div_blocked) -> None:
        """След ручного обхода заслона. Аудит не критичен для отправки, но без
        него потом не ответить на вопрос «почему письмо ушло вопреки заслону»."""
        try:
            self._store.append_audit(
                action="confirm_force_send", actor_user_id=actor_user_id,
                entity_type="confirm_review", entity_id=review_id,
                detail={"operator": operator, "email": row.get("email"),
                        "inn": row.get("inn"),
                        "обойдено": [x for x in (blocked, div_blocked) if x]})
        except Exception:  # noqa: BLE001 - аудит не должен ронять отправку
            logger.exception("аудит ручного обхода не записался (review=%s)",
                             review_id)

    def edit(self, review_id: int, *, subject: Optional[str] = None,
             body: Optional[str] = None, operator: str = "",
             force: bool = False, actor_user_id=None,
             division: Optional[str] = None) -> bool:
        """Правка оператора: сохраняем текст И unified-диф (золотая пара).
        В live-режиме правленый текст уходит по SMTP немедленно; иначе — в
        очередь с новым текстом.

        force=True — тот же ручной обход заслонов, что в approve: оператор
        правит письмо и отправляет его вторым подтверждением."""
        row = self._require_pending(review_id)
        if row.get("kind") != "reply":
            blocked = self._guard(inn=row.get("inn"), email=row["email"])
            div_blocked = self._division_blocked(row)
            if (blocked or div_blocked) and force:
                self._audit_force(review_id, row, operator, actor_user_id,
                                  blocked, div_blocked)
            elif blocked:
                raise ConfirmBlockedError(
                    f"отправка запрещена ({blocked}) — правка не выпускает письмо")
            elif div_blocked:
                raise ConfirmBlockedError(f"гейт направлений: {div_blocked}")
        new_subject = subject if subject is not None else row["subject"]
        new_body = body if body is not None else row["body"]
        no_change = new_subject == row["subject"] and new_body == row["body"]
        diff = "" if no_change else build_diff(
            row["subject"], row["body"], new_subject, new_body)
        if self._sender is not None:
            # правку фиксируем как золотую пару ДО отправки (диф не потеряется,
            # даже если SMTP упадёт), затем шлём вживую
            self._send_live(row, new_subject, new_body, operator,
                            edited_subject=None if no_change else new_subject,
                            edited_body=None if no_change else new_body,
                            diff_text=diff or None, force=force,
                            prefer_division=division)
            return True
        if no_change:
            return self._store.confirm_decide(
                review_id, status="approved", decided_by=operator)
        return self._store.confirm_decide(
            review_id, status="edited", edited_subject=new_subject,
            edited_body=new_body, diff_text=diff, decided_by=operator)

    def _send_live(self, row: dict, subject: str, body: str, operator: str,
                   *, edited_subject: Optional[str] = None,
                   edited_body: Optional[str] = None,
                   diff_text: Optional[str] = None, force: bool = False,
                   prefer_division: Optional[str] = None):
        """Реальная немедленная отправка одного письма по SMTP (ручной путь).

        Для kind='reply' — ответ в тред через sender.send_reply (диалог, без
        окна/каденции); иначе — исходящее через sender.send(manual=True).
        Юр-гейты остаются внутри send/send_reply. Успех → review='sent'.
        """
        from sender.dtos import RenderedMessage
        if not self._store.confirm_claim_sending(row["id"]):
            raise ConfirmBlockedError(
                "письмо уже обрабатывается/обработано параллельным запросом")
        try:
            self._send_live_inner(row, subject, body, operator,
                                  edited_subject=edited_subject,
                                  edited_body=edited_body, diff_text=diff_text,
                                  force=force, prefer_division=prefer_division)
        except Exception:
            # SMTP/гейт не дал отправить — возвращаем на решение оператору
            self._store.confirm_release_sending(row["id"])
            raise

    def _send_live_inner(self, row: dict, subject: str, body: str,
                         operator: str, *, edited_subject=None,
                         edited_body=None, diff_text=None, force: bool = False,
                         prefer_division: Optional[str] = None):
        from sender.dtos import RenderedMessage
        if row.get("kind") == "reply":
            # ящик треда: на него клиент писал — отвечаем с него же
            prefer = None
            panel_j = row.get("panel") or {}
            if isinstance(panel_j, dict):
                prefer = panel_j.get("mailbox_id") or panel_j.get("inbox_mailbox")
            mailbox_id = self._fallback_mailbox(inn=row.get("inn"),
                                                prefer_mailbox=prefer)
            if mailbox_id is None:
                raise ConfirmBlockedError(
                    "нет доступного ящика НУЖНОГО НАПРАВЛЕНИЯ для ответа "
                    "(все на паузе/гейте или направление без своего ящика)")
            # Исключения (Suppressed/GateTripped/Send) всплывают оператору.
            self._sender.send_reply(
                to_email=row["email"], subject=subject, body=body,
                mailbox_id=mailbox_id, in_reply_to=row.get("in_reply_to"),
                thread_id=row.get("thread_id"),
                recipient_id=row.get("recipient_id"),
                # цепочка входящего: ответ встаёт В ВЕТКУ переписки клиента
                references=(panel_j.get("references")
                            if isinstance(panel_j, dict) else None))
            self._store.confirm_decide(
                row["id"], status="sent",
                edited_subject=edited_subject, edited_body=edited_body,
                diff_text=diff_text, decided_by=operator)
            return

        mid = row.get("message_id")
        if mid is None:
            raise ValidationError("нет message_id — нечего отправлять")
        message = self._store.get_message(mid)
        if message is None:
            raise ValidationError(f"message {mid} не найден")
        recipient = self._store.get_recipient(message.recipient_id)
        if recipient is None:
            raise ValidationError("получатель не найден")
        campaign = self._store.get_campaign(message.campaign_id)
        # Ревью #48: выбор ящика оператором (panel.mailbox_id из set_mailbox)
        # для ИСХОДЯЩИХ игнорировался — уважался только в ответах. Карточка
        # показывала «с ящика: X (оператор)», а письмо реально уходило с ящика,
        # который молча выбрал pick_mailbox. Теперь порядок как в send_as():
        # выбор оператора (если ящик доступен) → подбор → запасной путь.
        panel_out = row.get("panel") if isinstance(row.get("panel"), dict) else {}
        prefer_out = (panel_out or {}).get("mailbox_id") or None
        # тот же ключ, что показан оператору в карточке (send_as): направление
        # письма, а если его не определить - направление разбираемой очереди
        letter_div = self.letter_division(row) or (prefer_division or None)
        mailbox_id = None
        if prefer_out:
            mailbox_id = self._fallback_mailbox(inn=row.get("inn"),
                                                prefer_mailbox=prefer_out)
        if mailbox_id is None:
            mailbox_id = self._sender.pick_mailbox(recipient, campaign, manual=True)
            # Ротация ящиков (#59) остаётся за pick_mailbox, но направление
            # письма важнее: у компании «kc+meyer» гейт пропускает ОБА ящика,
            # и подбор мог выдать компрессорный под письмо про фотосепараторы
            # (карточка при этом показывала ящик из send_as — другой).
            # Правим ТОЛЬКО настоящее расхождение, иначе ротация выключилась бы
            # для всей исходящей почты.
            if mailbox_id is not None and letter_div and \
                    self._division_of_mailbox(mailbox_id) not in (None, letter_div):
                свой = self._fallback_mailbox(inn=row.get("inn"),
                                              prefer_division=letter_div)
                if свой:
                    mailbox_id = свой
        if mailbox_id is None:
            mailbox_id = self._fallback_mailbox(inn=row.get("inn"),
                                                prefer_division=letter_div)
        if mailbox_id is None:
            raise ConfirmBlockedError(
                "нет доступного ящика для отправки (все на паузе/лимите/гейте)")
        rendered = RenderedMessage(subject=subject, body=body)
        # Реальный SMTP. Исключения (Suppressed/GateTripped/Send/...) всплывают
        # оператору — письмо не ушло, review остаётся pending.
        # to_email=row["email"]: адрес из КАРТОЧКИ (оператор мог заменить) —
        # иначе письмо уходило на старый адрес получателя (ревью №40, критично)
        self._sender.send(message, rendered, mailbox_id, manual=True,
                          to_email=row.get("email") or None, force=force)
        # письмо sent (mark_sent внутри send). Фиксируем решение.
        self._store.confirm_decide(
            row["id"], status="sent",
            edited_subject=edited_subject, edited_body=edited_body,
            diff_text=diff_text, decided_by=operator)

    def submit_reply(
        self, *, reply_to: str, subject: str, body: str,
        in_reply_to: Optional[str] = None, thread_id: Optional[str] = None,
        recipient_id: Optional[int] = None, inn: Optional[str] = None,
        panel: Optional[dict] = None,
    ) -> SubmitResult:
        """Черновик ответа автоответчика в очередь подтверждений (kind='reply').

        Всегда pending (авто-отправки ответов нет — оператор жмёт «Отправить»).
        Заслон очереди: отписавшемуся/пожаловавшемуся ответ не готовим. Дедуп
        по треду (thread_id или адрес+тема), чтобы повторный входящий не плодил
        дубль-черновик.
        """
        blocked = self._guard(inn=inn, email=reply_to)
        # для ответа блокируем только на отписке/жалобе (не на «недавнем
        # контакте» — это диалог, инициированный клиентом)
        if blocked and blocked.startswith("suppressed:") and (
                "unsubscribe" in blocked or "complaint" in blocked):
            rid, created = self._store.confirm_submit(
                email=reply_to, subject=subject, body=body, kind="reply",
                in_reply_to=in_reply_to, thread_id=thread_id,
                recipient_id=recipient_id, inn=inn, panel=panel,
                status="skipped", reason=f"auto:{blocked}",
                dedup_key=self._reply_dedup(reply_to, thread_id))
            return SubmitResult(rid, created, "skipped", blocked)
        rid, created = self._store.confirm_submit(
            email=reply_to, subject=subject, body=body, kind="reply",
            in_reply_to=in_reply_to, thread_id=thread_id,
            recipient_id=recipient_id, inn=inn, panel=panel,
            dedup_key=self._reply_dedup(reply_to, thread_id))
        return SubmitResult(rid, created, "pending")

    @staticmethod
    def _reply_dedup(reply_to: str, thread_id: Optional[str]) -> str:
        key = thread_id or (reply_to or "").strip().lower()
        return f"reply|{key}"

    # Товарная лексика направлений — зеркало ai_letter._EQUIP_MARKERS. Держим
    # копию, чтобы confirm не тянул генератор ради двух кортежей.
    _LETTER_DIV_MARKERS = {
        "kc": ("компрессор", "азот", "кислород", " мкс", "пневмо", "воздуходув"),
        "meyer": ("рентген", "фотосепар", "фото-сепар", "инспекц", "сортировк"),
    }

    def letter_division(self, row: dict) -> Optional[str]:
        """kc|meyer|None — про КАКОЕ направление письмо в этой карточке.

        Компания бывает «kc+meyer», но письмо всегда про ОДНО направление
        (ai_letter.target_division: «компания с потребностью в обоих получает
        ОДНО письмо про ОДИН товар»). Ящик обязан совпадать с письмом, иначе
        письмо про фотосепараторы уходит с компрессорного адреса и с подписью
        менеджера КЦ — направление у ящика своё, и гейт его не ловит, потому
        что компании разрешены оба.

        Источники по убыванию надёжности:
          1) panel.letter_division — направление, выбранное генератором;
          2) лексика самого письма — для писем, которые легли в очередь до
             того, как п.1 стали записывать (на 28.07 это вся очередь).
        """
        panel = row.get("panel") if isinstance(row.get("panel"), dict) else {}
        d = str((panel or {}).get("letter_division") or "").strip().lower()
        if d in ("kc", "meyer"):
            return d
        letter = (panel or {}).get("letter")
        текст = " ".join([
            str(row.get("subject") or ""), str(row.get("body") or ""),
            str((letter or {}).get("subject") or "") if isinstance(letter, dict) else "",
            str((letter or {}).get("body") or "") if isinstance(letter, dict) else "",
        ]).lower()
        if not текст.strip():
            return None
        попало = {k for k, ms in self._LETTER_DIV_MARKERS.items()
                  if any(m in текст for m in ms)}
        # обе лексики сразу — не гадаем: пусть решает обычный подбор
        return next(iter(попало)) if len(попало) == 1 else None

    def _next_in_rotation(self, candidates: list) -> Optional[str]:
        """Следующий ящик по кругу за последним реально отправлявшим.

        Тот же смысл, что у Sender.pick_mailbox (#59, владелец: «не с одного
        всё отправлялось, а с разных по очереди»), но круг считается ВНУТРИ
        переданного набора: у Meyer четыре ящика против четырнадцати
        компрессорных, и глобальный указатель почти всегда указывал бы на
        чужой ящик — тогда Meyer-круг вечно начинался бы с первого адреса.
        Указатель durable (события sent/reply_sent), переживает рестарт.
        """
        if not candidates:
            return None
        last = None
        getter = getattr(self._store, "last_sent_mailbox", None)
        if callable(getter):
            try:
                last = getter(among=list(candidates))
            except TypeError:      # Store старой версии — без among
                last = getter()
            except Exception:      # noqa: BLE001 — подбор важнее указателя
                last = None
        if last and last in candidates:
            return candidates[(candidates.index(last) + 1) % len(candidates)]
        return candidates[0]

    def _division_of_mailbox(self, mailbox_id: str) -> Optional[str]:
        try:
            for mb in self._sender.config.mailboxes():
                if mb.mailbox_id == mailbox_id:
                    return getattr(mb, "division", None)
        except Exception:  # noqa: BLE001
            pass
        return None

    def _fallback_mailbox(self, *, inn=None, prefer_mailbox=None,
                          prefer_division=None) -> Optional[str]:
        """Ящик для ручной отправки/ответа. Ревью №5/№16/№37: раньше брался
        ПЕРВЫЙ доступный — ответ клиенту уходил с чужого ящика и мимо гейта
        направлений (Meyer-клиенту могло ответить компрессорное направление,
        а тред у клиента ломался: писал одному адресу, ответ пришёл с другого).

        Порядок предпочтения:
          1) ящик, на который клиент писал (prefer_mailbox) — тред сохраняется;
          2) любой ящик ПОДХОДЯЩЕГО направления (по потребностям компании);
          3) любой доступный — только если направление неизвестно.
        Пауза/гейт/лимит проверяются на каждом шаге."""
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)
        try:
            boxes = list(self._sender.config.mailboxes())
        except Exception:  # noqa: BLE001
            return None

        def _ok(mid):
            try:
                return self._sender.can_send_now(mid, now=now, manual=True)
            except Exception:  # noqa: BLE001
                return False

        # 1) ящик из треда
        if prefer_mailbox and any(mb.mailbox_id == prefer_mailbox for mb in boxes) \
                and _ok(prefer_mailbox):
            return prefer_mailbox

        # 2) ящик нужного направления
        allowed = None
        cards = self._cards
        if inn and cards is not None and getattr(cards, "active", False):
            getter = getattr(cards, "divisions", None)
            if callable(getter):
                allowed = getter(inn)
            if allowed is None:
                d = cards.division(inn)
                allowed = {p for p in str(d or "").split("+") if p}
        if allowed:
            # prefer_division — нужное направление (письма либо очереди, которую
            # разбирает оператор). Гейт им НЕ расширяем: перебираем по-прежнему
            # только ящики внутри allowed. Но внутри разрешённого нужное
            # направление идёт первым — у компании «kc+meyer» подходят оба, и
            # без этого всегда выигрывал первый по конфигу, то есть КЦ.
            годные = [mb.mailbox_id for mb in boxes
                      if getattr(mb, "division", None) in allowed
                      and _ok(mb.mailbox_id)]
            if prefer_division:
                свои = [mb.mailbox_id for mb in boxes
                        if getattr(mb, "division", None) == prefer_division
                        and mb.mailbox_id in годные]
                if свои:
                    return self._next_in_rotation(свои)
            if годные:
                return self._next_in_rotation(годные)
            # направление известно, но своего ящика нет — молча слать с чужого
            # нельзя: оператор должен увидеть причину (нет ящика Meyer и т.п.)
            return None

        # 3) У КОМПАНИИ направление неизвестно (её нет в базе обзвона, либо
        # индекс не поднят). Это не повод игнорировать направление ПИСЬМА:
        # письмо про фотосепараторы всё равно должно уйти с Meyer-ящика.
        # Раньше здесь брался просто первый доступный ящик — то есть всегда
        # компрессорный, и в очереди Meyer подставлялся КЦ (владелец 28.07,
        # ООО «Контрольный пакет»: компании нет в базе обзвона).
        # Гейт этим не ослабляется: право слать такой компании проверяет
        # division_block/_division_blocked на отправке, а не этот подбор.
        свободные = [mb.mailbox_id for mb in boxes if _ok(mb.mailbox_id)]
        if prefer_division:
            свои = [mb.mailbox_id for mb in boxes
                    if getattr(mb, "division", None) == prefer_division
                    and mb.mailbox_id in свободные]
            if свои:
                return self._next_in_rotation(свои)
        return self._next_in_rotation(свободные)

    def send_as(self, row: dict, *, prefer_division: Optional[str] = None) -> dict:
        """С КАКОГО ЯЩИКА уйдёт это письмо — и какие ещё можно выбрать.

        Раньше оператор этого не видел вовсе: ящик подбирался молча внутри
        approve, а в карточке подпись стояла с заглушкой вместо имени
        менеджера. Подтверждая живую отправку живому юрлицу, оператор должен
        видеть отправителя и иметь возможность его сменить.

        Считаем ЖИВЬЁМ на каждый показ очереди, а не при генерации: пауза,
        лимит и гейт ящика меняются в течение дня, и вчерашний выбор мог уже
        протухнуть. Ручной выбор оператора (panel.mailbox_id) уважаем первым.
        """
        panel = row.get("panel") if isinstance(row.get("panel"), dict) else {}
        manual = (panel or {}).get("mailbox_id") or None
        # Направление ПИСЬМА решает, с какого ящика оно должно уйти. У компании
        # «оба направления» без этого подставлялся первый по конфигу, то есть
        # всегда компрессорный, даже когда оператор разбирает очередь Meyer.
        letter_div = self.letter_division(row)
        # Направление письма — главный ключ. Если его не определить (старое
        # письмо без метки, нейтральная лексика), берём направление очереди,
        # которую разбирает оператор: он открыл Meyer — значит и отправитель
        # должен быть Meyer. Ровно этот же ключ уходит в реальную отправку.
        нужное = letter_div or (prefer_division or None)
        chosen = self._fallback_mailbox(inn=row.get("inn"),
                                        prefer_mailbox=manual,
                                        prefer_division=нужное)
        try:
            boxes = list(self._sender.config.mailboxes())
        except Exception:  # noqa: BLE001
            boxes = []
        # какие направления допустимы этой компании — показываем оператору
        # только подходящие ящики, чтобы Meyer-клиенту не ушло от компрессорных
        allowed = None
        cards = self._cards
        inn = row.get("inn")
        if inn and cards is not None and getattr(cards, "active", False):
            try:
                getter = getattr(cards, "divisions", None)
                allowed = getter(inn) if callable(getter) else None
                if allowed is None:
                    d = cards.division(inn)
                    allowed = {p for p in str(d or "").split("+") if p}
            except Exception:  # noqa: BLE001
                allowed = None
        from datetime import datetime as _dt, timezone as _tz
        now = _dt.now(_tz.utc)
        opts = []
        for mb in boxes:
            div = getattr(mb, "division", None)
            if allowed and div not in allowed:
                continue
            try:
                # now — обязательный именованный аргумент; без него вызов падал
                # и ВСЕ ящики помечались недоступными, хотя подбор их берёт.
                # manual=True: оператор шлёт осознанно, окно и пейсинг не
                # применяются, а пауза/лимит/kill-switch остаются.
                ok = self._sender.can_send_now(mb.mailbox_id, now=now, manual=True)
            except Exception:  # noqa: BLE001
                ok = False
            # у ящиков mailbox_id и есть адрес — показываем его оператору,
            # иначе в списке одни имена и непонятно, с какого домена уйдёт
            addr = (getattr(mb, "email", "") or getattr(mb, "address", "")
                    or mb.mailbox_id)
            opts.append({"mailbox_id": mb.mailbox_id,
                         "from_name": getattr(mb, "from_name", "") or "",
                         "email": addr,
                         "division": div, "available": bool(ok)})
        # Порядок в выпадашке: сперва ящики направления ПИСЬМА, затем — того
        # направления, чью очередь оператор сейчас разбирает (prefer_division
        # из фильтра КЦ/Meyer), затем остальные. Оператору Meyer не нужно
        # пролистывать четырнадцать компрессорных адресов, чтобы найти свои.
        # Сортировка стабильная: внутри групп порядок конфига сохраняется.
        opts.sort(key=lambda o: 0 if (letter_div and o["division"] == letter_div)
                  else 1 if (prefer_division and o["division"] == prefer_division)
                  else 2)
        cur = next((o for o in opts if o["mailbox_id"] == chosen), None)
        return {
            "mailbox_id": chosen,
            "from_name": (cur or {}).get("from_name", ""),
            "email": (cur or {}).get("email", ""),
            "source": "оператор" if manual else "подбор",
            # направление ВЫБРАННОГО ящика — по нему панель собирает подпись
            "division": (cur or {}).get("division"),
            "letter_division": letter_div,
            "options": opts,
            "note": ("" if chosen else
                     "нет доступного ящика нужного направления — "
                     "все на паузе, лимите или гейте"),
        }

    def set_mailbox(self, review_id: int, mailbox_id: str, *,
                    operator: str = "") -> dict:
        """Зафиксировать ящик отправки, выбранный оператором (panel.mailbox_id).

        Тот же ключ читает approve/ответ в ветке — то есть выбор реально влияет
        на отправку, а не только на отображение."""
        row = self._require_pending(review_id)
        ids = {mb.mailbox_id for mb in self._sender.config.mailboxes()}
        if mailbox_id not in ids:
            raise ValidationError(f"ящик {mailbox_id!r} не настроен")
        panel = row.get("panel") if isinstance(row.get("panel"), dict) else {}
        panel = dict(panel or {})
        panel["mailbox_id"] = mailbox_id
        self._store.confirm_set_panel(review_id, panel)
        try:
            self._store.append_audit(
                action="confirm.mailbox", actor_user_id=None,
                entity_type="confirm_review", entity_id=review_id,
                detail={"mailbox_id": mailbox_id, "operator": operator})
        except Exception:  # noqa: BLE001
            pass
        return self._store.confirm_get(review_id)

    def skip(self, review_id: int, *, reason: str, operator: str = "") -> bool:
        if not (reason or "").strip():
            raise ValidationError("skip требует причину")
        self._require_pending(review_id)
        return self._store.confirm_decide(
            review_id, status="skipped", reason=reason.strip(),
            decided_by=operator)

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
