# -*- coding: utf-8 -*-
"""Лента событий по-человечески: что случилось и за что.

БЫЛО. В ленте стояли коды: sent, bounce, suppress, reply_auto,
reject_spam. Оператор видел «bounce» и не знал ни за что отбивка, ни какому
адресу — причина лежала в detail_json, куда панель не смотрела вовсе.
Владелец 25.08.2026: «сделай, чтобы человекопонятно было — отбивка, за что
отбивка, письмо отправлено и так далее».

СТАЛО. Тип переводится словами, а рядом идёт короткая причина, собранная из
того, что реально лежит в detail (ключи сверены по базе 25.08, а не
угаданы): у отбивки — диагностика SMTP и адрес, у стоп-листа — за что
внесли, у пропуска — почему не слали, у ответа — метка разбора.

ПРАВИЛО ЧЕСТНОСТИ. Незнакомый код НЕ прячем: показываем как есть. Пустая
клетка лучше выдуманной причины, а выдуманный перевод хуже английского.
"""
from __future__ import annotations

import re
from typing import Any, Optional

ЯРЛЫКИ = {
    "sent": "письмо отправлено",
    "delivered": "письмо доставлено",
    "open": "письмо открыли",
    "bounce": "отбивка — письмо не дошло",
    "reject_spam": "почтовик не принял письмо",
    "complaint": "жалоба на спам",
    "reply": "ответ клиента",
    "reply_auto": "автоответ клиента",
    "reply_sent": "мы ответили",
    "suppress": "адрес в стоп-листе",
    "unsubscribe": "отписка",
    "skip": "письмо пропущено",
    "retry_scheduled": "назначен повтор",
    "division_gate_block": "заслон направления",
    "other": "входящее вне переписки",
}

# Диагностика SMTP словами. Порядок важен: сначала точные признаки, потом
# общие — «mailbox unavailable» бывает и у переполненного ящика.
_ОТБИВКИ = (
    (r"no such user|invalid mailbox|user unknown|unknown user|"
     r"адресат не найден|5\.1\.1", "такого ящика нет"),
    (r"mailbox full|quota exceeded|over quota|переполн", "ящик переполнен"),
    (r"spam|5\.7\.1|blacklist|blocked", "получатель принял за спам"),
    (r"domain not found|unrouteable|no mx|5\.4\.4|host not found",
     "домен не принимает почту"),
    (r"greylist|4\.7\.1|try again later|4\.2\.0", "сервер просит повторить позже"),
    (r"policy|запрещ|not allowed|refused", "запрет политикой получателя"),
    (r"disabled|inactive|отключ", "ящик отключён"),
)

_СТОП_ЛИСТ = {
    "bounce_hard": "жёсткая отбивка",
    "bounce": "отбивка",
    "complaint": "жалоба на спам",
    "unsubscribe": "отписался",
    "manual": "внесён вручную",
    "deal_in_progress": "сделка уже в работе",
}

_ПРОПУСК = {
    "replied": "клиент уже ответил",
    "suppressed": "адрес в стоп-листе",
    "duplicate": "такому уже писали",
    "no_data": "не хватило данных для письма",
    "gate": "не пустил гейт репутации",
}

_ПОВТОР = {
    "soft_bounce": "мягкая отбивка",
    "transient": "временный сбой почтовика",
}


def yarlyk(event_type: str) -> str:
    """Тип события словами. Незнакомый код возвращаем как есть."""
    return ЯРЛЫКИ.get(str(event_type or "").strip(), str(event_type or ""))


def _pervaya_stroka(текст: Any, предел: int = 90) -> str:
    т = " ".join(str(текст or "").split())
    return т[:предел]


def _diagnoz(текст: str) -> str:
    """Строку SMTP-диагностики — в короткую причину словами."""
    т = str(текст or "")
    for образец, словами in _ОТБИВКИ:
        if re.search(образец, т, re.I):
            return словами
    return ""


def pochemu(event_type: str, detail: Optional[dict]) -> str:
    """Короткая причина события. Пусто — значит причины и нет (обычная отправка)."""
    d = detail if isinstance(detail, dict) else {}
    т = str(event_type or "")

    if т == "bounce":
        dsn = d.get("dsn") if isinstance(d.get("dsn"), dict) else {}
        диаг = str(dsn.get("diagnostic") or "")
        куда = ""
        сбой = dsn.get("failed")
        if isinstance(сбой, (list, tuple)) and сбой:
            куда = str(сбой[0])
        словами = _diagnoz(диаг) or _pervaya_stroka(
            re.sub(r"^smtp;\s*", "", диаг), 70)
        if куда and словами:
            return "%s: %s" % (куда, словами)
        return словами or куда or _snippet_stroka(d)

    if т == "reject_spam":
        ошибка = str(d.get("error") or "")
        кто = "Яндекс" if "ya.cc" in ошибка or "yandex" in ошибка.lower() else "почтовик"
        return "%s не принял письмо: подозрение на спам" % кто

    if т == "suppress":
        причина = str(d.get("reason") or "")
        адреса = d.get("addresses")
        адрес = str(адреса[0]) if isinstance(адреса, (list, tuple)) and адреса else ""
        словами = _СТОП_ЛИСТ.get(причина, причина)
        return ("%s: %s" % (адрес, словами)).strip(": ") if адрес else словами

    if т == "skip":
        причина = str(d.get("reason") or "")
        return _ПРОПУСК.get(причина, причина)

    if т == "retry_scheduled":
        причина = _ПОВТОР.get(str(d.get("reason") or ""), str(d.get("reason") or ""))
        глубина = d.get("depth")
        return ("%s, попытка %s" % (причина, глубина)) if глубина else причина

    if т in ("reply", "reply_auto", "complaint", "other"):
        метка = str(d.get("reply_kind") or "")
        текст = _pervaya_stroka(d.get("snippet"), 80)
        if метка and текст:
            return "%s — %s" % (метка, текст)
        return метка or текст

    if т == "reply_sent":
        как = "написан руками из веб-почты" if d.get("ruchnoy") else "отправлен из панели"
        тема = _pervaya_stroka(d.get("tema"), 60)
        return ("%s: %s" % (как, тема)) if тема else как

    return _pervaya_stroka(d.get("reason") or d.get("error") or "", 80)


def _snippet_stroka(d: dict) -> str:
    return _pervaya_stroka(d.get("snippet"), 70)
