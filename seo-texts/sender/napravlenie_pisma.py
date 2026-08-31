# -*- coding: utf-8 -*-
"""Про какое направление ПИСЬМО — один разборщик на оба пути отправки.

ЗАЧЕМ ОТДЕЛЬНЫЙ МОДУЛЬ. Направление письма спрашивают два слоя, и до
21.08 каждый спрашивал по-своему:

  * ручной экран (confirm.ConfirmSend.letter_division) — сначала поле
    panel.letter_division от генератора, а если его нет, ТОВАРНАЯ ЛЕКСИКА
    самого письма;
  * авто-отправка (sender.Sender._napravlenie_pisma) — только поле, плюс
    метка компании из карточки; лексику письма не смотрел вовсе.

Из-за этой разницы ящик подбирался по-разному. 20.08 копии второму
контакту «Гастрофабрики» ушли с компрессорных адресов
(m.pavlov@kompressor-pro-trade.ru, v.melnikov@kompressor-air-trade.ru) под
мейеровским письмом про рентген-инспекцию и оптическую сортировку: у
карточек копий поля letter_division не оказалось, ручной путь спас бы их
лексикой, а авто-путь промолчал — и подпись ушла «Компрессор Центр».
Владелец: «когда вручную делал копии и отправлял, отправил не проверив
направление».

Правило одно: поле генератора → лексика письма → не знаем (None). «Не
знаем» не значит «можно любой ящик»: у вызывающего есть свои запасные
источники (метка компании), и они остаются на своей стороне.
"""
from __future__ import annotations

from typing import Optional

# Товарная лексика направлений — зеркало ai_letter._EQUIP_MARKERS. Держим
# копию, чтобы ни confirm, ни sender не тянули генератор ради двух кортежей.
МАРКЕРЫ = {
    "kc": ("компрессор", "азот", "кислород", " мкс", "пневмо", "воздуходув"),
    "meyer": ("рентген", "фотосепар", "фото-сепар", "инспекц", "сортировк"),
}


def po_leksike(текст: str) -> Optional[str]:
    """kc|meyer|None по товарной лексике. Обе сразу — не гадаем."""
    т = str(текст or "").lower()
    if not т.strip():
        return None
    попало = {k for k, ms in МАРКЕРЫ.items() if any(m in т for m in ms)}
    return next(iter(попало)) if len(попало) == 1 else None


def napravlenie_pisma(row: dict) -> Optional[str]:
    """kc|meyer|None — про КАКОЕ направление письмо в этой карточке.

    Компания бывает «kc+meyer», но письмо всегда про ОДНО направление
    (ai_letter.target_division). Ящик обязан совпадать с письмом: подпись и
    домен строятся по направлению ЯЩИКА, и мейеровское письмо с
    компрессорного адреса получатель читает как чужую подпись.

    Источники по убыванию надёжности:
      1) panel.letter_division — направление, выбранное генератором;
      2) лексика самого письма — для карточек, которым поле не проставили:
         письма старше поля, часть новостных и КОПИИ вторым контактам.
    """
    if not isinstance(row, dict):
        return None
    panel = row.get("panel") if isinstance(row.get("panel"), dict) else {}
    d = str((panel or {}).get("letter_division") or "").strip().lower()
    if d in МАРКЕРЫ:
        return d
    letter = (panel or {}).get("letter")
    if not isinstance(letter, dict):
        letter = {}
    return po_leksike(" ".join([
        str(row.get("subject") or ""), str(row.get("body") or ""),
        str(row.get("body_rendered") or ""),
        str(row.get("edited_subject") or ""), str(row.get("edited_body") or ""),
        str(letter.get("subject") or ""), str(letter.get("body") or ""),
    ]))
