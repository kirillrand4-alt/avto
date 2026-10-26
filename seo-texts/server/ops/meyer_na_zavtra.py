# -*- coding: utf-8 -*-
"""Наступившие одобренные письма Meyer — на завтрашнее утро (владелец 26.10: «по кц
опять отправок 20 минут нету»). Все рабочие ящики Meyer выбрали дневной лимит
(70/70), а ~770 его писем в голове очереди: проход берёт каждое, не находит ящика
и возвращает — КЦ ждёт по 20+ минут. Ставим им время «завтра 02:00 UTC + секунды»
(05:00 МСК), порядок сохраняем. Журнал _ops/meyer-na-zavtra.jsonl, --otkat.
    meyer_na_zavtra.py [--primenit | --otkat]"""
import io
import json
import sqlite3
import sys
from datetime import datetime, timedelta

ЖУР = r"C:\sender\_ops\meyer-na-zavtra.jsonl"
c = sqlite3.connect(r"C:\sender\sender.db", timeout=120)
if "--otkat" in sys.argv:
    з = [json.loads(s) for s in io.open(ЖУР, encoding="utf-8")]
    with c:
        for x in reversed(з):
            c.execute("UPDATE messages SET scheduled_at=? WHERE id=? AND status='scheduled' AND scheduled_at=?",
                      (x["bylo"], x["id"], x["stalo"]))
    print("откат:", len(з))
    sys.exit()
кам = [r[0] for r in c.execute("SELECT id, name FROM campaigns") if "meyer" in str(r[1]).lower() or "мейер" in str(r[1]).lower()]
сейчас = datetime.utcnow()
ОДОБР = "(SELECT cr.status FROM confirm_reviews cr WHERE cr.message_id=m.id ORDER BY cr.id DESC LIMIT 1) IN ('approved','edited')"
ряды = c.execute("SELECT m.id, m.scheduled_at FROM messages m WHERE m.status='scheduled' AND m.scheduled_at<=? AND m.campaign_id IN (%s) AND %s "
                 "ORDER BY m.scheduled_at, m.id" % (",".join(map(str, кам)), ОДОБР), (сейчас.strftime("%Y-%m-%dT%H:%M:%S"),)).fetchall()
база = (сейчас + timedelta(days=1)).replace(hour=2, minute=0, second=0, microsecond=0)
print("наступивших одобренных Meyer:", len(ряды), "| перенос на", база)
if "--primenit" not in sys.argv:
    print("СУХОЙ ПРОГОН. Применить — --primenit")
    sys.exit()
with c, io.open(ЖУР, "a", encoding="utf-8") as ж:
    for i, (mid, было) in enumerate(ряды):
        стало = (база + timedelta(seconds=i)).strftime("%Y-%m-%dT%H:%M:%S.%f")
        c.execute("UPDATE messages SET scheduled_at=? WHERE id=? AND status='scheduled'", (стало, mid))
        ж.write(json.dumps({"id": mid, "bylo": было, "stalo": стало}) + "\n")
print("ПРИМЕНЕНО")
