# -*- coding: utf-8 -*-
"""Что успела сделать перепись старых кампаний: журнал и статусы карточек."""
import io
import json
import os
import sqlite3
from collections import Counter

ЖУРНАЛ = r"C:\sender\_ops\perepisat-starye.jsonl"
if os.path.exists(ЖУРНАЛ):
    строки = [json.loads(s) for s in io.open(ЖУРНАЛ, encoding="utf-8")
              if s.strip()]
    print(f"журнал: {len(строки)} записей")
    print("итоги:", dict(Counter(str(z.get("метка") or "").split(":")[0]
                                 for z in строки)))
    for z in строки[-5:]:
        print(f"  #{z.get('id')} {str(z.get('фирма'))[:32]:<32} "
              f"{str(z.get('метка'))[:60]}")
else:
    print("журнала нет — ни одно письмо не переписано")

c = sqlite3.connect(r"C:\sender\sender.db")
c.row_factory = sqlite3.Row
print("\nкарточки старых кампаний по статусу:")
for s, n in c.execute("SELECT status, COUNT(*) n FROM confirm_reviews "
                      "WHERE campaign_id NOT IN (10,11) AND id BETWEEN 900 AND 1200 "
                      "GROUP BY status ORDER BY n DESC"):
    print(f"  {s:<12} {n}")
