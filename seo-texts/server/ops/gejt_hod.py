# -*- coding: utf-8 -*-
"""Идёт ли гейт адресата: сколько вердиктов в target_verdicts за последний час."""
import sqlite3
c = sqlite3.connect(r"C:\sender\sender.db", timeout=30)
кол = [r[1] for r in c.execute("PRAGMA table_info(target_verdicts)")]
print("колонки:", кол)
вр = next((к for к in кол if к in ("ts", "created_at", "updated_at", "checked_at")), None)
if вр:
    for r in c.execute("SELECT substr(%s,1,16), count(*) FROM target_verdicts WHERE %s >= datetime('now','-2 hours') "
                       "GROUP BY substr(%s,1,15) ORDER BY 1" % (вр, вр, вр)):
        print(r)
print("=== ГЕЙТ ХОД ===")
