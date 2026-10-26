# -*- coding: utf-8 -*-
"""Статусы карточек пилота напоминаний (по журналу). Только чтение."""
import io
import json
import sqlite3
from collections import Counter
з = [json.loads(s) for s in io.open(r"C:\sender\_ops\napominaniya-pilot.jsonl", encoding="utf-8")]
c = sqlite3.connect(r"C:\sender\sender.db", timeout=60)
сч, прич = Counter(), Counter()
for x in з:
    r = c.execute("SELECT status, reason, kind, message_id FROM confirm_reviews WHERE id=?", (x.get("karta"),)).fetchone()
    if not r:
        сч["нет карточки"] += 1
        continue
    сч[r[0]] += 1
    if r[1]:
        прич[str(r[1])[:90]] += 1
print("карточек:", len(з), dict(сч))
print("причины:", прич.most_common(10))
print("пример:", c.execute("SELECT id, kind, status, reason, message_id, decided_at, panel_json FROM confirm_reviews WHERE id=?", (з[0].get("karta"),)).fetchone())
