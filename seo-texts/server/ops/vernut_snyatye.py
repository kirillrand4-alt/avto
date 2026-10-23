# -*- coding: utf-8 -*-
"""Вернуть снятые (skipped) письма в очередь автоотправки, тексты уже одобрены
(владелец 23.10: «верни» — сняты старым правилом «уже писали» в день письма на
другой адрес компании; с 23.10 другой адрес — через 3 дня).
Журнал _ops/vernut-snyatye.jsonl, --otkat возвращает skipped.
    vernut_snyatye.py id,id,... [--katit | --otkat]"""
import io
import json
import sqlite3
import sys
from datetime import datetime, timezone

ЖУР = r"C:\sender\_ops\vernut-snyatye.jsonl"
c = sqlite3.connect(r"C:\sender\sender.db", timeout=90)
ид = [int(x) for x in sys.argv[1].split(",")]
if "--otkat" in sys.argv:
    with c:
        for i in ид:
            c.execute("UPDATE messages SET status='skipped', last_error='откат vernut_snyatye' WHERE id=? AND status='scheduled'", (i,))
    print("откат:", ид)
    sys.exit()
кам = {r[0]: r[1] for r in c.execute("SELECT id, name FROM campaigns")}
сейчас = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000000")
ж = io.open(ЖУР, "a", encoding="utf-8")
for i in ид:
    r = c.execute("SELECT m.id, m.status, m.campaign_id, m.scheduled_at, m.last_error, lower(r.email), m.subject "
                  "FROM messages m JOIN recipients r ON r.id=m.recipient_id WHERE m.id=?", (i,)).fetchone()
    print(r[0], r[1], кам.get(r[2]), r[5], "|", (r[6] or "")[:60], "|", r[4])
    if "--katit" in sys.argv and r[1] == "skipped":
        with c:
            c.execute("UPDATE messages SET status='scheduled', scheduled_at=?, last_error=NULL, updated_at=? WHERE id=? AND status='skipped'",
                      (сейчас, сейчас, i))
        ж.write(json.dumps({"id": i, "bylo": r[1], "bylo_sched": r[3], "bylo_err": r[4]}, ensure_ascii=False) + "\n")
        print("   -> в очереди")
