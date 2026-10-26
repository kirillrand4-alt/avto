# -*- coding: utf-8 -*-
"""Одобренные письма Meyer из автоотправки — обратно в «Подтвердить отправку»
(владелец 26.10: «верни в подтвердить отправку мейер тогда, это проще, чем
править панель»). Ящики Meyer выбрали лимит, а их письма в очереди тормозят КЦ.
Письмо scheduled -> pending_review, карточка approved/edited -> pending.
Журнал _ops/meyer-v-podtverdit.jsonl; --otkat возвращает как было.
    meyer_v_podtverdit.py [--primenit | --otkat]"""
import io
import json
import sqlite3
import sys
from collections import Counter

ЖУР = r"C:\sender\_ops\meyer-v-podtverdit.jsonl"
c = sqlite3.connect(r"C:\sender\sender.db", timeout=120)
if "--otkat" in sys.argv:
    з = [json.loads(s) for s in io.open(ЖУР, encoding="utf-8")]
    with c:
        for x in з:
            c.execute("UPDATE confirm_reviews SET status=? WHERE id=? AND status='pending'", (x["karta_bylo"], x["karta"]))
            c.execute("UPDATE messages SET status='scheduled' WHERE id=? AND status='pending_review'", (x["id"],))
    print("откат:", len(з))
    sys.exit()
кам = {r[0]: r[1] for r in c.execute("SELECT id, name FROM campaigns") if "meyer" in str(r[1]).lower() or "мейер" in str(r[1]).lower()}
ряды = c.execute("SELECT m.id, m.campaign_id, cr.id, cr.status FROM messages m JOIN confirm_reviews cr ON cr.id = "
                 "(SELECT id FROM confirm_reviews WHERE message_id=m.id ORDER BY id DESC LIMIT 1) "
                 "WHERE m.status='scheduled' AND m.campaign_id IN (%s) AND cr.status IN ('approved','edited')"
                 % ",".join(map(str, кам))).fetchall()
print("одобренных писем Meyer в автоотправке:", len(ряды), dict(Counter(кам[r[1]] for r in ряды)))
if "--primenit" not in sys.argv:
    print("СУХОЙ ПРОГОН. Применить — --primenit")
    sys.exit()
with c, io.open(ЖУР, "a", encoding="utf-8") as ж:
    for mid, cid, kid, kst in ряды:
        c.execute("UPDATE messages SET status='pending_review' WHERE id=? AND status='scheduled'", (mid,))
        c.execute("UPDATE confirm_reviews SET status='pending' WHERE id=?", (kid,))
        ж.write(json.dumps({"id": mid, "karta": kid, "karta_bylo": kst}) + "\n")
print("ПРИМЕНЕНО:", len(ряды))
