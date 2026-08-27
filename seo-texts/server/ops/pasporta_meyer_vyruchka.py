# -*- coding: utf-8 -*-
"""Свежие паспорта сайтов: чьи это компании и какая у них выручка.

Владелец: «добавили новых паспортов мейер, какая выручка у компаний, в
среднем». Паспорт живёт в enrich.db/site_facts, выручка — в карточке
компании из базы обзвона (fin.revenue / vyruchka).
"""
import json
import os
import sqlite3
import sys
from collections import Counter

sys.path.insert(0, r"C:\sender\sender")
sys.path.insert(0, r"C:\sender")

ОБОГ = r"C:\sender\enrich.db"
o = sqlite3.connect("file:%s?mode=ro" % ОБОГ, uri=True, timeout=30)
o.row_factory = sqlite3.Row
кол = [r[1] for r in o.execute("PRAGMA table_info(site_facts)")]
print("колонки site_facts: %s" % ", ".join(кол))
всего = o.execute("SELECT COUNT(*) FROM site_facts").fetchone()[0]
print("паспортов всего: %d" % всего)
поле_вр = next((к for к in ("ts", "updated_at", "created_at", "when_ts")
                if к in кол), None)
print("поле времени: %s" % (поле_вр or "НЕТ"))
if поле_вр:
    print("")
    print("=== по дням ===")
    for r in o.execute("SELECT substr(%s,1,10) д, COUNT(*) n FROM site_facts "
                       " GROUP BY д ORDER BY д DESC LIMIT 10" % поле_вр):
        print("   %s  %d" % (r["д"], r["n"]))
o.close()
