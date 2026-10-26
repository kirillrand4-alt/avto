# -*- coding: utf-8 -*-
"""Meyer обратно в автоотправку ВПЕРЕМЕЖКУ с КЦ (владелец 26.10: «мейер вперемежку
подтверди в автоотправку»). Карточки, снятые meyer_v_podtverdit.py, снова
approved, письма scheduled; затем наступившим одобренным письмам КЦ и Meyer
время ставится через одно (К, М, К, М…) от «самое раннее в очереди минус N
секунд» — проход берёт оба направления поровну, и Meyer у лимита не загораживает
КЦ. Журнал _ops/vperemeshku.jsonl; --otkat возвращает время (одобрение — нет).
    meyer_kc_vperemeshku.py [--primenit | --otkat]"""
import io
import json
import sqlite3
import sys
from datetime import datetime, timedelta
from itertools import zip_longest

ЖУР = r"C:\sender\_ops\vperemeshku.jsonl"
c = sqlite3.connect(r"C:\sender\sender.db", timeout=120)
if "--otkat" in sys.argv:
    з = [json.loads(s) for s in io.open(ЖУР, encoding="utf-8")]
    with c:
        for x in reversed(з):
            c.execute("UPDATE messages SET scheduled_at=? WHERE id=? AND status='scheduled' AND scheduled_at=?", (x["bylo"], x["id"], x["stalo"]))
    print("откат времени:", len(з))
    sys.exit()
сн = [json.loads(s) for s in io.open(r"C:\sender\_ops\meyer-v-podtverdit.jsonl", encoding="utf-8")]
кам = {r[0]: r[1] for r in c.execute("SELECT id, name FROM campaigns")}
мей = {k for k, v in кам.items() if "meyer" in str(v).lower() or "мейер" in str(v).lower()}
сейчас = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S")
ОДОБР = "(SELECT cr.status FROM confirm_reviews cr WHERE cr.message_id=m.id ORDER BY cr.id DESC LIMIT 1) IN ('approved','edited')"
if "--primenit" not in sys.argv:
    print("снято в подтверждение ранее:", len(сн), "| СУХОЙ ПРОГОН. Применить — --primenit")
    sys.exit()
with c:
    вернули = 0
    for x in сн:
        if c.execute("UPDATE confirm_reviews SET status=? WHERE id=? AND status='pending'", (x["karta_bylo"], x["karta"])).rowcount:
            c.execute("UPDATE messages SET status='scheduled' WHERE id=? AND status='pending_review'", (x["id"],))
            вернули += 1
print("Meyer снова в автоотправке:", вернули)
ряды = c.execute("SELECT m.id, m.campaign_id, m.scheduled_at FROM messages m WHERE m.status='scheduled' AND m.scheduled_at<=? AND %s "
                 "ORDER BY m.scheduled_at, m.id" % ОДОБР, (сейчас,)).fetchall()
к = [r for r in ряды if r[1] not in мей]
м = [r for r in ряды if r[1] in мей]
порядок = [r for пара in zip_longest(к, м) for r in пара if r]
мин = c.execute("SELECT MIN(scheduled_at) FROM messages WHERE status='scheduled'").fetchone()[0]
база = datetime.fromisoformat(str(мин)[:19]) - timedelta(seconds=len(порядок) + 5)
with c, io.open(ЖУР, "a", encoding="utf-8") as ж:
    for i, (mid, cid, было) in enumerate(порядок):
        стало = (база + timedelta(seconds=i)).strftime("%Y-%m-%dT%H:%M:%S.%f")
        c.execute("UPDATE messages SET scheduled_at=? WHERE id=? AND status='scheduled'", (стало, mid))
        ж.write(json.dumps({"id": mid, "bylo": было, "stalo": стало}) + "\n")
print("вперемежку: КЦ %d, Meyer %d" % (len(к), len(м)))
