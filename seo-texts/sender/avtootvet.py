# -*- coding: utf-8 -*-
"""Автоответ как лид: вытащить новый адрес и переслать по нему то же письмо.

Зачем. 11.08 владелец спросил, почему ответ из ящика не попал в лиды. Ответ
оказался такой: письмо было автоответом (заголовок Auto-Submitted:
auto-replied), и классификатор отработал верно. Но внутри лежало то, ради чего
мы вообще пишем:

    Гладиум:      «нахожусь в отпуске, обращайтесь к Александру Белоусу
                   belous.a@gladium.ru»
    Фармоборона:  «создан единый общий адрес client@farmoborona.ru, просим
                   направлять все письма на указанный»

За месяц автоответов было два, и НОВЫЙ АДРЕС был в обоих. То есть это не
редкий случай, а правило: автоответ либо даёт замену, либо говорит, куда
писать. Раньше такое письмо молча уходило в события и не показывалось никому.

Что делает модуль:
  1. достаёт из текста адреса, которые могут быть новым контактом — свои
     домены, служебные autoreply@ и адрес самого отправителя отсеиваются;
  2. берёт ПОСЛЕДНЕЕ письмо, которое мы этому получателю отправили, и кладёт
     его копию в очередь подтверждений на новый адрес.

Копия, а не новая генерация: человек в отпуске или просит писать на общий
ящик — содержание письма от этого не меняется, а лишний вызов провайдера и
риск получить другой текст не нужны. Оператор видит письмо целиком и решает.
"""
from __future__ import annotations

import logging
import re
from typing import Any, Optional

logger = logging.getLogger(__name__)

_АДРЕС = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
# Наши собственные домены отправки: адрес из подписи нашего же письма,
# процитированного в автоответе, новым контактом не является.
_СВОИ = re.compile(r"(?i)(kompressor|compressor|meyer|usort|zernosort|"
                   r"sort-systems|optic-sort|prokompressor|rusprom|"
                   r"parsercompressor)")
# Служебные адреса самой системы автоответов.
_СЛУЖЕБНЫЕ = re.compile(r"(?i)(autoreply|auto-reply|noreply|no-reply|"
                        r"mailer-daemon|postmaster|do-?not-?reply)")


def адреса_из_автоответа(текст: str, *, от_кого: str = "",
                         свои: Optional[set] = None) -> list:
    """Адреса из автоответа, годные как новый контакт. Порядок — как в тексте.

    Отсеиваем: наши домены (в автоответе часто процитировано наше письмо),
    служебные autoreply@ и адрес самого отправителя — он и так известен.
    """
    свои = {str(x).strip().lower() for x in (свои or set())}
    отправитель = ""
    м = _АДРЕС.search(str(от_кого or ""))
    if м:
        отправитель = м.group(0).lower()
    найдено, видели = [], set()
    for а in _АДРЕС.findall(str(текст or "")):
        низ = а.lower()
        if низ in видели:
            continue
        видели.add(низ)
        if низ == отправитель or низ in свои:
            continue
        if _СЛУЖЕБНЫЕ.search(низ) or _СВОИ.search(низ):
            continue
        найдено.append(низ)
    return найдено


def _последнее_письмо(store: Any, recipient_id: int) -> Optional[dict]:
    """Что мы этому получателю отправили в последний раз (тема и тело).

    Берём отредактированный оператором текст, если он есть: именно его человек
    и получил, а не то, что сочинил генератор.
    """
    try:
        строка = store.poslednee_otpravlennoe(int(recipient_id))
    except Exception:  # noqa: BLE001
        logger.exception("автоответ: не нашлось последнее письмо получателя %s",
                         recipient_id)
        return None
    if not строка:
        return None
    return {"subject": строка.get("edited_subject") or строка.get("subject") or "",
            "body": строка.get("edited_body") or строка.get("body") or "",
            "campaign_id": строка.get("campaign_id"),
            "inn": строка.get("inn")}


def завести_получателя(store: Any, *, адрес: str,
                       образец_id: Optional[int] = None) -> Optional[int]:
    """Строка получателя для нового адреса, с реквизитами компании-образца.

    Без неё письмо висит в очереди «ничьим»: панель раскладывает очередь ПО
    ГРУППЕ ПОЛУЧАТЕЛЯ, и письмо без строки не видно ни под одним фильтром.
    Поймано 11.08: письма на belous.a@gladium.ru и client@farmoborona.ru
    легли в очередь и пропали с глаз — оператор искал их и не находил.
    """
    адрес = (адрес or "").strip().lower()
    if "@" not in адрес:
        return None
    try:
        готовый = store.get_recipient_by_email(адрес) if hasattr(
            store, "get_recipient_by_email") else None
        if готовый is not None:
            return int(getattr(готовый, "id", 0)) or None
    except Exception:  # noqa: BLE001
        pass
    образец = None
    if образец_id:
        try:
            образец = store.get_recipient(int(образец_id))
        except Exception:  # noqa: BLE001
            образец = None
    try:
        from sender.store import RecipientIn
        поле = dict(email=адрес, domain=адрес.split("@")[-1],
                    inn=getattr(образец, "inn", None),
                    company_name=getattr(образец, "company_name", None),
                    okved=getattr(образец, "okved", None),
                    segment=getattr(образец, "segment", None),
                    region=getattr(образец, "region", None),
                    source="avtootvet-perenapravlenie")
        поля = set(getattr(RecipientIn, "__dataclass_fields__", {}) or
                   getattr(RecipientIn, "model_fields", {}) or {})
        return int(store.upsert_recipient(RecipientIn(
            **{k: v for k, v in поле.items() if k in поля})))
    except Exception:  # noqa: BLE001
        logger.exception("автоответ: строка получателя для %s не завелась", адрес)
        return None


def переслать_на_новый_адрес(store: Any, *, recipient_id: int, адрес: str,
                             откуда: str = "") -> Optional[int]:
    """Положить копию последнего письма в очередь на новый адрес.

    Возвращает id строки очереди или None. Ничего не отправляет: письмо ждёт
    подтверждения оператором ровно как всякое другое.
    """
    письмо = _последнее_письмо(store, recipient_id)
    if not письмо or not письмо["body"]:
        logger.info("автоответ: копию слать нечего — исходного письма нет (%s)",
                    recipient_id)
        return None
    причина = ("автоответ дал новый адрес"
               + (f": {откуда}" if откуда else ""))
    # Строка получателя обязана появиться ДО постановки письма: очередь
    # раскладывается по группе получателя, и письмо без строки не видно.
    новый_id = завести_получателя(store, адрес=адрес, образец_id=recipient_id)
    try:
        from sender.store import Store  # noqa: F401  (для типа; не обязателен)
        rid, создано = store.confirm_submit(
            email=адрес, subject=письмо["subject"], body=письмо["body"],
            inn=письмо.get("inn"), campaign_id=письмо.get("campaign_id"),
            recipient_id=int(новый_id or recipient_id), status="pending",
            reason=причина,
            panel={"perenapravleno": True, "ishodnyy_poluchatel": int(recipient_id),
                   "pochemu": причина},
            dedup_key=f"avtootvet:{recipient_id}:{адрес.lower()}")
        logger.info("автоответ: копия письма поставлена в очередь на %s (%s)",
                    адрес, "новая" if создано else "уже была")
        return int(rid)
    except Exception:  # noqa: BLE001 - приём входящих важнее этой добавки
        logger.exception("автоответ: копия на %s не поставилась", адрес)
        return None


def разобрать_автоответ(store: Any, *, recipient_id: Optional[int],
                        текст: str, от_кого: str = "",
                        свои: Optional[set] = None) -> dict:
    """Полный разбор: найти адреса и поставить копии писем на них.

    Возвращает {'адреса': [...], 'постановки': [id, ...]} — этим же словарём
    помечается лид, чтобы оператор видел, что нашлось.
    """
    адреса = адреса_из_автоответа(текст, от_кого=от_кого, свои=свои)
    постановки = []
    if recipient_id:
        for а in адреса:
            rid = переслать_на_новый_адрес(store, recipient_id=int(recipient_id),
                                           адрес=а, откуда=от_кого)
            if rid:
                постановки.append(rid)
    return {"адреса": адреса, "постановки": постановки}
