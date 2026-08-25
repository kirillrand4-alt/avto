# -*- coding: utf-8 -*-
"""Ручные ответы из веб-почты: подобрать из «Отправленных» и завести в диалог.

ЗАЧЕМ. Оператор отвечает клиенту прямо из веб-интерфейса почтовика, минуя
панель. Для системы такого ответа не существует: карточка лида остаётся
пустой, стол ответов может предложить черновик тому, кому уже ответили, а в
переписке компании зияет дыра между входящим и следующим письмом. Владелец
25.08.2026: «я в итоге вручную в ящики зашёл, написал ответы».

КАК ОТЛИЧАЕМ СВОЁ ОТ РУЧНОГО. По Message-ID: письма, отправленные панелью,
лежат в messages.rfc_message_id. Признак проверен 25.08 — из 3462 писем в
«Отправленных» 3419 совпали с нашими.

ЦЕНА ОБХОДА. Всю папку каждый тик не гоняем: помним наибольший UID и
спрашиваем только новые (UID last+1:*). Первый заход после рестарта берёт
последние сутки — этого хватает, чтобы не потерять вчерашний ответ и не
перечитать три тысячи писем.

НИЧЕГО НЕ ЛОМАЕТ. Сбор только читает (readonly-select) и глушит свои
ошибки: не подобрали ручной ответ — потеряли удобство, а не письмо.
"""
from __future__ import annotations

import email
import email.policy
import imaplib
import logging
import os
import re
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from typing import Any, Iterable, Optional

from sender.v_otpravlennye import nayti_papku

logger = logging.getLogger(__name__)

_МЕСЯЦЫ = ("Jan", "Feb", "Mar", "Apr", "May", "Jun",
           "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


def _data_dlya_imap(когда: datetime) -> str:
    """IMAP-дата вида 24-Aug-2026 (только латинские месяцы, без локали)."""
    return "%02d-%s-%d" % (когда.day, _МЕСЯЦЫ[когда.month - 1], когда.year)


def _adres(строка: str) -> str:
    """Голый адрес из заголовка «Имя <a@b.ru>»."""
    м = re.search(r"[\w.+-]+@[\w.-]+\.\w+", str(строка or ""))
    return м.group(0).lower() if м else ""


def _kogda(zagolovok: Any) -> datetime:
    """Date письма -> aware UTC. Кривой или пустой заголовок — берём «сейчас»:
    время нужно для порядка в диалоге, и ради него ронять подбор незачем."""
    try:
        т = parsedate_to_datetime(str(zagolovok))
    except Exception:  # noqa: BLE001
        return datetime.now(timezone.utc)
    if т is None:
        return datetime.now(timezone.utc)
    return т if т.tzinfo else т.replace(tzinfo=timezone.utc)


def razobrat(raw: bytes) -> dict:
    """Письмо из папки -> поля, которыми живёт диалог."""
    msg = email.message_from_bytes(raw, policy=email.policy.default)
    тело = ""
    if msg.is_multipart():
        for часть in msg.walk():
            if часть.get_content_type() == "text/plain":
                тело = часть.get_content()
                break
    else:
        тело = msg.get_content() if msg.get_content_type() == "text/plain" else ""
    return {
        "rfc_message_id": (msg.get("Message-ID") or "").strip(),
        "komu": _adres(msg.get("To", "")),
        "ot": _adres(msg.get("From", "")),
        "tema": str(msg.get("Subject") or "").strip(),
        "in_reply_to": (msg.get("In-Reply-To") or "").strip() or None,
        "references": (msg.get("References") or "").strip(),
        "kogda": _kogda(msg.get("Date")),
        "telo": (тело or "")[:4000],
    }


def sobrat(mb_cfg: Any, *, nash_li, s_uid: int = 0, dney: int = 1,
           opener=None, predel: int = 100) -> tuple[list[dict], int]:
    """Ручные письма из «Отправленных» ящика.

    nash_li(message_id) -> bool: письмо отправлено панелью, брать не надо.
    Возвращает (письма, наибольший увиденный UID) — UID хранит вызывающий.
    """
    пароль = os.getenv(getattr(mb_cfg, "password_env", "") or "", "")
    if not пароль:
        return [], s_uid
    imap = None
    найдено: list[dict] = []
    верх = s_uid
    try:
        if opener is not None:
            imap = opener(mb_cfg)
        else:
            imap = imaplib.IMAP4_SSL(mb_cfg.imap_host, mb_cfg.imap_port, timeout=25)
            imap.login(mb_cfg.login, пароль)
        папка = nayti_papku(imap)
        if not папка:
            return [], s_uid
        тип, _ = imap.select(папка, readonly=True)
        if тип != "OK":
            return [], s_uid
        if s_uid:
            крит = ("UID", "%d:*" % (s_uid + 1))
        else:
            с = datetime.now(timezone.utc) - timedelta(days=max(1, int(dney)))
            крит = ("SINCE", _data_dlya_imap(с))
        тип, данные = imap.uid("SEARCH", None, *крит)
        if тип != "OK" or not данные:
            return [], s_uid
        uids = [u for u in (данные[0] or b"").split()][-predel:]
        for uid in uids:
            try:
                н = int(uid)
            except (TypeError, ValueError):
                continue
            верх = max(верх, н)
            if н <= s_uid:            # «UID n:*» всегда возвращает хотя бы один
                continue
            тип, куски = imap.uid("FETCH", uid, "(RFC822)")
            if тип != "OK" or not куски or not isinstance(куски[0], tuple):
                continue
            письмо = razobrat(куски[0][1])
            mid = письмо.get("rfc_message_id") or ""
            if not mid or nash_li(mid):
                continue              # это наше письмо, панель его уже знает
            письмо["uid"] = н
            найдено.append(письмо)
        return найдено, верх
    except Exception:  # noqa: BLE001 - подбор не смеет ронять сторожа
        logger.exception("ручные ответы: не собрались (%s)",
                         getattr(mb_cfg, "mailbox_id", "?"))
        return найдено, верх
    finally:
        if imap is not None:
            try:
                imap.logout()
            except Exception:  # noqa: BLE001
                pass


def chey_otvet(store: Any, pismo: dict) -> Optional[int]:
    """Кому этот ручной ответ — номер получателя или None.

    Сперва по ветке: у ответа в In-Reply-To/References лежит Message-ID
    НАШЕГО письма, а по нему messages сразу отдаёт получателя. Это точный
    путь, и он же единственный надёжный — отвечаем мы на адрес, С КОТОРОГО
    написал человек, а он часто не тот, на который слали (blumbakh.al@szgc.ru
    против omelenchuk.av@szgc.ru).

    Ветки нет — пробуем адрес как есть. Домен в запас не берём: у публичных
    почтовиков он не значит ничего, а у своего адрес и так найдётся.
    """
    по_ветке = getattr(store, "find_message_by_rfc_id", None)
    if callable(по_ветке):
        цепочка = []
        if pismo.get("in_reply_to"):
            цепочка.append(pismo["in_reply_to"])
        цепочка.extend(str(pismo.get("references") or "").split())
        for mid in цепочка:
            mid = mid.strip()
            if not mid:
                continue
            try:
                наше = по_ветке(mid)
            except Exception:  # noqa: BLE001
                наше = None
            rid = getattr(наше, "recipient_id", None) if наше else None
            if rid:
                return int(rid)
    по_адресу = getattr(store, "find_recipient_by_email", None)
    if callable(по_адресу) and pismo.get("komu"):
        try:
            р = по_адресу(pismo["komu"])
        except Exception:  # noqa: BLE001
            р = None
        if р:
            rid = r_id(р)
            if rid:
                return rid
    return None


def r_id(рек: Any) -> Optional[int]:
    """id получателя, кем бы он ни пришёл — объектом или словарём."""
    з = getattr(рек, "id", None)
    if з is None and isinstance(рек, dict):
        з = рек.get("id")
    try:
        return int(з) if з is not None else None
    except (TypeError, ValueError):
        return None


def podpisi(письма: Iterable[dict]) -> list[str]:
    """Короткая сводка для лога — что именно подобрали."""
    return ["%s -> %s: %s" % (п.get("ot"), п.get("komu"),
                              (п.get("tema") or "")[:40]) for п in письма]
