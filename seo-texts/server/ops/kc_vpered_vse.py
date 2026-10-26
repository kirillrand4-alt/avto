# -*- coding: utf-8 -*-
"""Письма КЦ — в начало очереди автоотправки (владелец 26.10: «почему он дальше
не отправляет кц?» — ящики Meyer у дневного лимита, 768 наступивших писем Meyer
в голове очереди, проход в 400 писем до КЦ не доходит). Наступившим одобренным
письмам КЦ ставим время «самое раннее в очереди минус секунды». Журнал
_ops/kc-vpered-vse.jsonl, --otkat.
    kc_vpered_vse.py [--primenit | --otkat]"""
import io
import json
import sqlite3
import sys
from datetime import datetime, timedelta

ЖУР = r"C:\sender\_ops\kc-vpered-vse.jsonl"
c = sqlite3.connect(r"C:\sender\sender.db", timeout=120)
if "--otkat" in sys.argv:
    з = [json.loads(s) for s in io.open(ЖУР, encoding="utf-8")]
    with c:
        for x in reversed(з):
            c.execute("UPDATE messages SET scheduled_at=? WHERE id=? AND status='scheduled'", (x["bylo"], x["id"]))
    print("откат:", len(з))
    sys.exit()
кам = [r[0] for r in c.execute("SELECT id, name FROM campaigns") if not ("meyer" in str(r[1]).lower() or "мейер" in str(r[1]).lower())]
сейчас = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S")
ОДОБР = "(SELECT cr.status FROM confirm_reviews cr WHERE cr.message_id=m.id ORDER BY cr.id DESC LIMIT 1) IN ('approved','edited')"
мин = c.execute("SELECT MIN(m.scheduled_at) FROM messages m WHERE m.status='scheduled' AND m.scheduled_at<=? AND " + ОДОБР,
                (сейчас,)).fetchone()[0]
ряды = c.execute("SELECT m.id, m.scheduled_at FROM messages m WHERE m.status='scheduled' AND m.scheduled_at<=? AND m.campaign_id IN (%s) AND %s "
                 "ORDER BY m.scheduled_at, m.id" % (",".join(map(str, кам)), ОДОБР), (сейчас,)).fetchall()
база = datetime.fromisoformat(str(мин)[:19]) - timedelta(seconds=len(ряды) + 5)
print("самое раннее в очереди:", мин, "| писем КЦ наступивших одобренных:", len(ряды))
if "--primenit" not in sys.argv:
    print("СУХОЙ ПРОГОН. Применить — --primenit")
    sys.exit()
with c, io.open(ЖУР, "a", encoding="utf-8") as ж:
    for i, (mid, было) in enumerate(ряды):
        стало = (база + timedelta(seconds=i)).strftime("%Y-%m-%dT%H:%M:%S.%f")
        c.execute("UPDATE messages SET scheduled_at=? WHERE id=? AND status='scheduled'", (стало, mid))
        ж.write(json.dumps({"id": mid, "bylo": было, "stalo": стало}) + "\n")
print("ПРИМЕНЕНО")
