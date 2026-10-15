# -*- coding: utf-8 -*-
"""Кампания «КЦ тест — КЦ» для генерации по группе «КЦ тест» (владелец 15.10:
«запускай»). Копия кампании 14 («Россия 9000 — Meyer»): статус, юрлицо, шаг
последовательности — но config.segment=kc , пул как у 14, чтобы заслоны
направления (campaign_vs_mailbox) выдали письмам ящики КЦ. Идемпотентно.

    kampaniya_kc_test.py [--primenit]
"""
import json
import sqlite3
import sys
import time

ИМЯ = sys.argv[sys.argv.index("--imya") + 1] if "--imya" in sys.argv else "КЦ тест — КЦ"
c = sqlite3.connect(r"C:\sender\sender.db", timeout=60)
c.row_factory = sqlite3.Row
есть = c.execute("SELECT id FROM campaigns WHERE name=?", (ИМЯ,)).fetchone()
if есть:
    print("уже есть: id %d" % есть[0])
    print("=== КАМПАНИЯ КЦ ТЕСТ ===")
    sys.exit(0)
об = dict(c.execute("SELECT * FROM campaigns WHERE id=?", (15 if "--imya" in sys.argv else 14,)).fetchone())
print("образец 14:", об["name"], об["status"], об["provider_pool"], об["config_json"])
for k in (10,):
    р = c.execute("SELECT id,name,status,provider_pool,config_json FROM campaigns WHERE id=?", (k,)).fetchone()
    print("кампания 10:", tuple(р) if р else None)
if "--primenit" not in sys.argv:
    print("=== КАМПАНИЯ КЦ ТЕСТ: сухой прогон ===")
    sys.exit(0)
конф = json.loads(об["config_json"] or "{}") or {}
конф["segment"] = "kc"
т = time.strftime("%Y-%m-%dT%H:%M:%S")
with c:
    cur = c.execute("INSERT INTO campaigns (name,status,legal_entity,legal_inn,provider_pool,config_json,created_at,"
                    "started_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?)",
                    (ИМЯ, об["status"], об["legal_entity"], об["legal_inn"], об["provider_pool"],
                     json.dumps(конф, ensure_ascii=False), т, об["started_at"] and т, т))
    нов = cur.lastrowid
    кол = [r[1] for r in c.execute("PRAGMA table_info(sequence_steps)") if r[1] != "id"]
    for шаг in c.execute("SELECT * FROM sequence_steps WHERE campaign_id=?", (об["id"],)).fetchall():
        д = dict(шаг)
        д["campaign_id"] = нов
        c.execute("INSERT INTO sequence_steps (%s) VALUES (%s)" % (",".join(кол), ",".join("?" * len(кол))),
                  [д[k] for k in кол])
print("создана кампания id %d (segment kc)" % нов)
print("=== КАМПАНИЯ КЦ ТЕСТ: СОЗДАНА ===")
