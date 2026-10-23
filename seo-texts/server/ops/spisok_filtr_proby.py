# -*- coding: utf-8 -*-
"""Отфильтровать список генерации (json id получателей) по пробе: вон
«неясно/отказ/мёртв» и уже имеющих письмо; «есть» первыми. Перезаписывает
файл. spisok_filtr_proby.py <путь к json>"""
import io
import json
import sqlite3
import sys

c = sqlite3.connect(r"C:\sender\sender.db")
проба = {str(r[0]).lower(): str(r[1] or "") for r in c.execute("SELECT email, verdict FROM addr_probe")}
ids = json.load(io.open(sys.argv[1]))
ряды, вон = [], {}
for rid in ids:
    r = c.execute("SELECT lower(email) FROM recipients WHERE id=?", (rid,)).fetchone()
    if not r or c.execute("SELECT 1 FROM messages WHERE recipient_id=?", (rid,)).fetchone():
        вон["нет/есть письмо"] = вон.get("нет/есть письмо", 0) + 1
        continue
    в = проба.get(r[0], "")
    if в in ("нет ящика", "нет MX", "неясно", "отказ пробе"):
        вон[в] = вон.get(в, 0) + 1
        continue
    ряды.append(({"есть": 0, "принимает всё": 1}.get(в, 2), rid))
json.dump([x[1] for x in sorted(ряды)], io.open(sys.argv[1], "w"))
print("в списке:", len(ряды), "| вон:", вон)
