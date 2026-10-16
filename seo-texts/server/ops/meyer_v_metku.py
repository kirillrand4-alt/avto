# -*- coding: utf-8 -*-
"""Карточки Meyer-кампании, которые гейт направлений держит («НАПРАВЛЕНИЯ НЕ
СОВПАДАЮТ: кампания meyer, компании подходит kc»): дописать meyer в метку базы
обзвона (obzvon.division «kc» -> «kc+meyer»). КЦ-направление остаётся.
Старые метки — _ops/meyer-v-metku.jsonl. Откат: --otkat.
Без --primenit — только счёт."""
import io
import json
import sqlite3
import sys
import time

sys.path.insert(0, r"C:\sender")

ЖУРНАЛ = r"C:\sender\_ops\meyer-v-metku.jsonl"
o = sqlite3.connect(r"C:\sender\obzvon-index.db", timeout=60)
if "--otkat" in sys.argv:
    with o:
        for s in io.open(ЖУРНАЛ, encoding="utf-8"):
            z = json.loads(s)
            o.execute("UPDATE obzvon SET division=? WHERE inn=?", (z["bylo"], z["inn"]))
    print("откат сделан")
    sys.exit()
c = sqlite3.connect(r"C:\sender\sender.db", timeout=60)
инн = set()
for (i,) in c.execute("SELECT DISTINCT inn FROM confirm_reviews WHERE status='pending' AND campaign_id IN (14, 11, 8) AND inn IS NOT NULL"):
    row = o.execute("SELECT division FROM obzvon WHERE inn=?", (str(i),)).fetchone()
    if row and "meyer" not in str(row[0] or ""):
        инн.add(str(i))
print("карточек Meyer под гейтом, компаний:", len(инн))
if "--primenit" in sys.argv and инн:
    т = time.strftime("%Y-%m-%dT%H:%M:%S")
    n = 0
    with o, io.open(ЖУРНАЛ, "a", encoding="utf-8") as ж:
        for i in инн:
            row = o.execute("SELECT division FROM obzvon WHERE inn=?", (i,)).fetchone()
            if not row:
                continue
            было = row[0] or ""
            if "meyer" in было:
                continue
            стало = (было + "+meyer") if было else "meyer"
            o.execute("UPDATE obzvon SET division=? WHERE inn=?", (стало, i))
            ж.write(json.dumps({"inn": i, "bylo": было, "stalo": стало, "ts": т}, ensure_ascii=False) + "\n")
            n += 1
    print("метка дописана:", n)
