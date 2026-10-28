# -*- coding: utf-8 -*-
"""Снять «просроченные» письма без карточки подтверждения (владелец 28.10:
«снимай»): scheduled, дата раньше сегодня, ни одной карточки — автоотправка их
никогда не возьмёт. -> skipped, last_error с причиной. Журнал
_ops/snyat-bez-kartochki.jsonl, --otkat -> scheduled обратно.
    snyat_bez_kartochki.py [--primenit | --otkat]"""
import io
import json
import sqlite3
import sys
from datetime import datetime

ЖУР = r"C:\sender\_ops\snyat-bez-kartochki.jsonl"
c = sqlite3.connect(r"C:\sender\sender.db", timeout=60)
if "--otkat" in sys.argv:
    з = [json.loads(s) for s in io.open(ЖУР, encoding="utf-8")]
    with c:
        for x in з:
            c.execute("UPDATE messages SET status='scheduled', last_error=NULL WHERE id=? AND status='skipped'", (x["id"],))
    print("откат:", len(з))
    sys.exit()
ряды = c.execute("SELECT m.id FROM messages m WHERE m.sent_at IS NULL AND m.status='scheduled' "
                 "AND coalesce(m.scheduled_at,'')<>'' AND substr(m.scheduled_at,1,10) < date('now') "
                 "AND NOT EXISTS (SELECT 1 FROM confirm_reviews cr WHERE cr.message_id=m.id)").fetchall()
print("писем без карточки с прошедшей датой:", len(ряды))
if "--primenit" not in sys.argv:
    print("СУХОЙ ПРОГОН")
    sys.exit()
т = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S")
with c, io.open(ЖУР, "a", encoding="utf-8") as ж:
    for (mid,) in ряды:
        c.execute("UPDATE messages SET status='skipped', last_error=?, updated_at=? WHERE id=? AND status='scheduled'",
                  ("снято 28.10 (владелец): нет карточки подтверждения", т, mid))
        ж.write(json.dumps({"id": mid}) + "\n")
print("ПРИМЕНЕНО:", len(ряды))
