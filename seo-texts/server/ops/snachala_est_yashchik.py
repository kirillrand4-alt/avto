# -*- coding: utf-8 -*-
"""Письма на адреса, где проба подтвердила ящик, — первыми (владелец 20.10:
«сделай письма где точно есть ящик первыми на отправку»).

Время отправки не придумываем, а ПЕРЕСТАВЛЯЕМ: внутри каждой пары (ящик-
отправитель, часовой пояс получателя) берём те же самые значения scheduled_at,
сортируем и раздаём заново: сначала «есть», потом «принимает всё», «неясно»,
«не проверен», «отказ пробе». Темп ящика, лимиты и рабочие часы получателя не
меняются — меняется только порядок. Журнал — _ops/snachala-est-yashchik.jsonl.
    snachala_est_yashchik.py [--primenit | --otkat]"""
import io
import json
import sqlite3
import sys
from collections import Counter, defaultdict

ЖУР = r"C:\sender\_ops\snachala-est-yashchik.jsonl"
c = sqlite3.connect(r"C:\sender\sender.db", timeout=120)
if "--otkat" in sys.argv:
    зап = [json.loads(s) for s in io.open(ЖУР, encoding="utf-8")]
    with c:
        for z in reversed(зап):
            c.execute("UPDATE messages SET scheduled_at=? WHERE id=? AND status='scheduled'", (z["bylo"], z["id"]))
    print("откат:", len(зап))
    sys.exit()
РАНГ = {"есть": 0, "принимает всё": 1, "неясно": 2, "": 3, "отказ пробе": 4}
# Отправщик берёт письма ORDER BY scheduled_at, id (store.py), и почти вся
# очередь стоит на одно время (8:00 МСК) — порядок решал номер письма. Поэтому:
# * уже наступившие: все получают одно время «самое раннее из наступивших»
#   плюс ранг секундами — «есть» уходят первыми, раньше всех остальных;
# * будущие: своё время плюс ранг секундами — внутри своего часа «есть» первыми,
#   рабочие часы получателя не сдвигаются.
from datetime import datetime
сейчас = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.%f")
проба = {str(r[0]).lower(): str(r[1] or "") for r in c.execute("SELECT email, verdict FROM addr_probe")}
ряды = c.execute("SELECT m.id, r.email, m.scheduled_at FROM messages m JOIN recipients r ON r.id=m.recipient_id "
                 "WHERE m.status='scheduled' AND m.scheduled_at IS NOT NULL ORDER BY m.scheduled_at, m.id").fetchall()
наступ = [r for r in ряды if str(r[2]) <= сейчас]
база = min((str(r[2])[:19] for r in наступ), default=None)
правки = []
до, после = Counter(), Counter()


def _плюс(осн, сек):
    from datetime import timedelta
    return (datetime.fromisoformat(осн[:19]) + timedelta(seconds=сек)).strftime("%Y-%m-%dT%H:%M:%S.%f")


for mid, em, sa in ряды:
    ранг = РАНГ.get(проба.get(str(em).lower(), ""), 3)
    стало = _плюс(база, ранг) if str(sa) <= сейчас else _плюс(str(sa), ранг)
    if стало != sa:
        правки.append((mid, sa, стало))
    до[ранг] += 0
новый = sorted(((dict((p[0], p[2]) for p in правки).get(mid, sa), mid, РАНГ.get(проба.get(str(em).lower(), ""), 3)) for mid, em, sa in ряды))
for _, _, р in [(None, None, РАНГ.get(проба.get(str(em).lower(), ""), 3)) for _, em, _ in ряды[:len(ряды) // 3]]:
    до[р] += 1
for _, _, р in новый[:len(новый) // 3]:
    после[р] += 1
группы = {"все": ряды}
print("сейчас", сейчас[:19], "| наступивших", len(наступ), "| база", база)
имя = {v: k or "не проверен" for k, v in РАНГ.items()}
print("писем в расписании:", sum(len(v) for v in группы.values()), "| групп ящик+пояс:", len(группы))
print("первая треть очереди ДО:   ", {имя[k]: v for k, v in sorted(до.items())})
print("первая треть очереди ПОСЛЕ:", {имя[k]: v for k, v in sorted(после.items())})
print("писем поменяют время:", len(правки))
if "--primenit" not in sys.argv:
    print("СУХОЙ ПРОГОН. Применить — --primenit")
    sys.exit()
with c, io.open(ЖУР, "a", encoding="utf-8") as ж:
    for mid, было, стало in правки:
        c.execute("UPDATE messages SET scheduled_at=? WHERE id=? AND status='scheduled'", (стало, mid))
        ж.write(json.dumps({"id": mid, "bylo": было, "stalo": стало}) + "\n")
print("ПРИМЕНЕНО")
