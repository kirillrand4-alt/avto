# -*- coding: utf-8 -*-
"""Наступившие одобренные письма с пробой «есть» — в голову очереди, за ними
«принимает всё» (владелец 29.10: «переставь очерёдность»). Журнал
_ops/est-vpered.jsonl, --otkat.   est_vpered.py [--primenit | --otkat]"""
import io
import json
import sqlite3
import sys
from collections import Counter
from datetime import datetime, timedelta

ЖУР = r"C:\sender\_ops\est-vpered.jsonl"
c = sqlite3.connect(r"C:\sender\sender.db", timeout=120)
if "--otkat" in sys.argv:
    з = [json.loads(s) for s in io.open(ЖУР, encoding="utf-8")]
    with c:
        for x in reversed(з):
            c.execute("UPDATE messages SET scheduled_at=? WHERE id=? AND status='scheduled'", (x["bylo"], x["id"]))
    print("откат:", len(з))
    sys.exit()
проба = {str(r[0]).lower(): str(r[1] or "") for r in c.execute("SELECT email, verdict FROM addr_probe")}
сейчас = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S")
ОДОБР = "(SELECT cr.status FROM confirm_reviews cr WHERE cr.message_id=m.id ORDER BY cr.id DESC LIMIT 1) IN ('approved','edited')"
ряды = c.execute("SELECT m.id, m.scheduled_at, lower(r.email) FROM messages m JOIN recipients r ON r.id=m.recipient_id "
                 "WHERE m.status='scheduled' AND m.scheduled_at<=? AND %s ORDER BY m.scheduled_at, m.id" % ОДОБР, (сейчас,)).fetchall()
ранг = {"есть": 0, "принимает всё": 1}
ряды.sort(key=lambda r: ранг.get(проба.get(r[2], ""), 2))
print("наступивших одобренных:", len(ряды), dict(Counter(проба.get(r[2], "нет пробы") for r in ряды)))
if "--primenit" not in sys.argv:
    print("СУХОЙ ПРОГОН")
    sys.exit()
мин = c.execute("SELECT MIN(scheduled_at) FROM messages WHERE status='scheduled'").fetchone()[0] or сейчас
база = datetime.fromisoformat(str(мин)[:19]) - timedelta(seconds=len(ряды) + 5)
with c, io.open(ЖУР, "a", encoding="utf-8") as ж:
    for i, (mid, sa, em) in enumerate(ряды):
        c.execute("UPDATE messages SET scheduled_at=? WHERE id=? AND status='scheduled'", ((база + timedelta(seconds=i)).strftime("%Y-%m-%dT%H:%M:%S.%f"), mid))
        ж.write(json.dumps({"id": mid, "bylo": sa}) + "\n")
print("ПРИМЕНЕНО")
