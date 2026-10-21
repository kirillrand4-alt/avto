# -*- coding: utf-8 -*-
"""Кампания Meyer — копия кампании 14 («Россия 9000 — Meyer»): статус, юрлицо,
пул, конфиг (segment meyer-направления) и шаги. Идемпотентно по имени.
    kampaniya_meyer_kopiya.py "<имя>" [--primenit]"""
import json
import sqlite3
import sys
import time

ИМЯ = sys.argv[1]
c = sqlite3.connect(r"C:\sender\sender.db", timeout=60)
c.row_factory = sqlite3.Row
есть = c.execute("SELECT id FROM campaigns WHERE name=?", (ИМЯ,)).fetchone()
if есть:
    print("уже есть: id %d" % есть[0])
    sys.exit(0)
об = dict(c.execute("SELECT * FROM campaigns WHERE id=14").fetchone())
print("образец 14:", об["name"], об["status"], об["provider_pool"], об["config_json"])
if "--primenit" not in sys.argv:
    print("сухой прогон")
    sys.exit(0)
т = time.strftime("%Y-%m-%dT%H:%M:%S")
with c:
    cur = c.execute("INSERT INTO campaigns (name,status,legal_entity,legal_inn,provider_pool,config_json,created_at,started_at,updated_at) "
                    "VALUES (?,?,?,?,?,?,?,?,?)", (ИМЯ, об["status"], об["legal_entity"], об["legal_inn"], об["provider_pool"],
                                                   об["config_json"], т, об["started_at"] and т, т))
    нов = cur.lastrowid
    кол = [r[1] for r in c.execute("PRAGMA table_info(sequence_steps)") if r[1] != "id"]
    for шаг in c.execute("SELECT * FROM sequence_steps WHERE campaign_id=14").fetchall():
        з = dict(шаг)
        з["campaign_id"] = нов
        c.execute("INSERT INTO sequence_steps (%s) VALUES (%s)" % (",".join(кол), ",".join("?" * len(кол))), [з[k] for k in кол])
print("создана кампания id %d" % нов)
