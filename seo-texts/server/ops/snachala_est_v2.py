# -*- coding: utf-8 -*-
"""«Есть» первыми — по-настоящему (владелец 22.10: «ты точно передвинул?»).
snachala_est_yashchik.py прибавлял к времени письма ранг секундами: порядок
менялся только внутри одного часа, а «принимает всё» на 9:00 всё равно уходило
раньше «есть» на 11:00 — после перестановки ушло 41 «принимает всё» и 22 «есть».

Здесь времена МЕНЯЮТСЯ МЕСТАМИ: внутри каждой пары (ящик-отправитель, часовой
пояс получателя) берём все scheduled_at, сортируем и раздаём письмам в порядке
(ранг пробы, прежнее время). Набор времён у ящика и пояса тот же — темп, лимиты
и рабочие часы получателя не меняются. Журнал — _ops/snachala-est-v2.jsonl.
    snachala_est_v2.py [--primenit | --otkat]"""
import io
import json
import sqlite3
import sys
from collections import Counter, defaultdict

ЖУР = r"C:\sender\_ops\snachala-est-v2.jsonl"
c = sqlite3.connect(r"C:\sender\sender.db", timeout=120)
if "--otkat" in sys.argv:
    зап = [json.loads(s) for s in io.open(ЖУР, encoding="utf-8")]
    with c:
        for z in reversed(зап):
            c.execute("UPDATE messages SET scheduled_at=? WHERE id=? AND status='scheduled'", (z["bylo"], z["id"]))
    print("откат:", len(зап))
    sys.exit()
РАНГ = {"есть": 0, "принимает всё": 1, "": 2, "неясно": 3, "отказ пробе": 4}
проба = {str(r[0]).lower(): str(r[1] or "") for r in c.execute("SELECT email, verdict FROM addr_probe")}
ряды = c.execute("SELECT m.id, lower(r.email), m.scheduled_at, m.mailbox_id, r.tz FROM messages m "
                 "JOIN recipients r ON r.id=m.recipient_id WHERE m.status='scheduled' AND m.scheduled_at IS NOT NULL").fetchall()
гр = defaultdict(list)
for mid, em, sa, mb, tz in ряды:
    гр[(mb, tz)].append((РАНГ.get(проба.get(em, ""), 2), str(sa), mid))
правки = []
for к, пис in гр.items():
    времена = sorted(p[1] for p in пис)
    for (ранг, было, mid), стало in zip(sorted(пис), времена):
        if стало != было:
            правки.append((mid, было, стало))
имя = {v: k or "не проверен" for k, v in РАНГ.items()}
нов = dict((p[0], p[2]) for p in правки)
по_вр = sorted((нов.get(mid, str(sa)), РАНГ.get(проба.get(em, ""), 2)) for mid, em, sa, mb, tz in ряды)
до = sorted((str(sa), РАНГ.get(проба.get(em, ""), 2)) for mid, em, sa, mb, tz in ряды)
n = len(ряды) // 3
print("писем в расписании:", len(ряды), "| групп ящик+пояс:", len(гр), "| по вердикту:",
      {имя[k]: v for k, v in sorted(Counter(r for _, r in до).items())})
print("первая треть ДО:   ", {имя[k]: v for k, v in sorted(Counter(r for _, r in до[:n]).items())})
print("первая треть ПОСЛЕ:", {имя[k]: v for k, v in sorted(Counter(r for _, r in по_вр[:n]).items())})
print("писем поменяют время:", len(правки))
if "--primenit" not in sys.argv:
    print("СУХОЙ ПРОГОН. Применить — --primenit")
    sys.exit()
with c, io.open(ЖУР, "a", encoding="utf-8") as ж:
    for mid, было, стало in правки:
        c.execute("UPDATE messages SET scheduled_at=? WHERE id=? AND status='scheduled'", (стало, mid))
        ж.write(json.dumps({"id": mid, "bylo": было, "stalo": стало}) + "\n")
print("ПРИМЕНЕНО")
