# -*- coding: utf-8 -*-
"""Сколько отправленных писем ушло с мужским глаголом от женского ящика.

Владелец увидел письмо Анастасии Мирошниченко со словами «Разбирался,
чем занимается». Согласование по роду в панели есть, но словарь знает
«разобрался» и не знает «разбирался» - а именно эта форма стоит в списке
фраз знакомства.
"""
import re
import sqlite3
import sys
from collections import Counter

sys.path.insert(0, r"C:\sender")
from sender.config import Config                                 # noqa: E402
from sender.gender_agree import _FEM, gender_of                  # noqa: E402

cfg = Config.load(r"C:\sender\sender.yaml")
# Пол ящика: явная карта конфига, иначе по имени.
карта = cfg.get("personalization.mailbox_gender", None) or {}
пол = {}
for mb in cfg.mailboxes():
    имя = str(getattr(mb, "from_name", "") or getattr(mb, "name", "") or "")
    mid = str(getattr(mb, "mailbox_id", "") or "")
    я = карта.get(mid) if hasattr(карта, "get") else None
    пол[mid] = gender_of(имя, я)
    print(f"  ящик {mid:<44} имя «{имя}» -> {пол[mid]}")

женские = {m for m, g in пол.items() if str(g).lower() in ("f", "ж", "female")}
print(f"\nженских ящиков: {len(женские)} из {len(пол)}")

c = sqlite3.connect(r"C:\sender\sender.db")
c.row_factory = sqlite3.Row
# Мужская форма 1 лица прошедшего времени в начале предложения.
ГЛАГОЛ = re.compile(r"(?m)(?:^|[.!?»]\s+)([А-ЯЁ][а-яё]+(?:лся|л|ся))\b")
плохие = Counter()
писем = 0
всего = 0
for r in c.execute(
        "SELECT m.mailbox_id, cr.body, COALESCE(cr.edited_body,'') eb "
        "FROM messages m JOIN confirm_reviews cr ON cr.message_id=m.id "
        "WHERE m.status='sent'"):
    всего += 1
    if str(r["mailbox_id"]) not in женские:
        continue
    т = str(r["eb"] or r["body"] or "")
    нашли = set()
    for сл in ГЛАГОЛ.findall(т):
        н = сл.lower()
        if н.endswith(("ла", "лась")):
            continue
        if н in _FEM:            # словарь знает - значит согласование сработало
            continue
        if н.endswith(("лся", "л")):
            нашли.add(н)
    if нашли:
        писем += 1
        for н in нашли:
            плохие[н] += 1

print(f"\nотправлено всего: {всего}")
print(f"писем с женского ящика и мужским глаголом: {писем}")
for сл, n in плохие.most_common(20):
    print(f"  {n:>4}  {сл}")
