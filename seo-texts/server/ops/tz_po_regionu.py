# -*- coding: utf-8 -*-
"""Часовой пояс получателя по региону (владелец 23.10: «проставь время
получателя верно, если оно не верно»). Получатели с письмом в очереди
(scheduled/approved/sending) или карточкой pending: tz пустой или не совпадает
с regions.region_to_tz(region) — исправляем. Письмам в очереди, у которых
поменялся пояс, scheduled_at не трогаем (автоотправка сама переносит письмо
в окно получателя). Журнал _ops/tz-po-regionu.jsonl, --otkat.
    tz_po_regionu.py [--primenit | --otkat] [--vse]  (--vse — все получатели)"""
import io
import json
import sqlite3
import sys
import time
from collections import Counter

sys.path.insert(0, r"C:\sender")
from sender.regions import region_to_tz  # noqa: E402

ЖУР = r"C:\sender\_ops\tz-po-regionu.jsonl"
c = sqlite3.connect(r"C:\sender\sender.db", timeout=120)
if "--otkat" in sys.argv:
    з = [json.loads(s) for s in io.open(ЖУР, encoding="utf-8")]
    with c:
        for x in reversed(з):
            c.execute("UPDATE recipients SET tz=? WHERE id=?", (x["bylo"], x["id"]))
    print("откат:", len(з))
    sys.exit()
if "--vse" in sys.argv:
    ряды = c.execute("SELECT id, region, tz FROM recipients").fetchall()
else:
    ряды = c.execute("SELECT DISTINCT r.id, r.region, r.tz FROM recipients r WHERE r.id IN ("
                     "SELECT recipient_id FROM messages WHERE status IN ('scheduled','approved','sending') "
                     "UNION SELECT recipient_id FROM confirm_reviews WHERE status='pending')").fetchall()
сч, пр, правки = Counter(), Counter(), []
for rid, рег, tz in ряды:
    нов = region_to_tz(рег) if рег else None
    if not нов:
        сч["регион не распознан — не трогаем"] += 1
        continue
    if tz == нов:
        сч["пояс верный"] += 1
        continue
    сч["исправить: было %s" % (tz or "пусто")] += 1
    пр["%s → %s" % (tz or "пусто", нов)] += 1
    правки.append((нов, rid, tz))
print("получателей:", len(ряды))
for k, v in сч.most_common():
    print("  %6d  %s" % (v, k))
print("переходы:", пр.most_common(10))
if "--primenit" in sys.argv:
    т = time.strftime("%Y-%m-%dT%H:%M:%S")
    with c, io.open(ЖУР, "a", encoding="utf-8") as ж:
        for нов, rid, было in правки:
            c.execute("UPDATE recipients SET tz=?, updated_at=? WHERE id=?", (нов, т, rid))
            ж.write(json.dumps({"id": rid, "bylo": было, "stalo": нов}) + "\n")
    print("ПРИМЕНЕНО:", len(правки))
