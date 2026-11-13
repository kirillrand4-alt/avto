# -*- coding: utf-8 -*-
"""Кампания 23: станция «под резку» — (а) у писем, где фраза про компанию НЕ о резке, заменить на общий охват по газу;
(б) у остальных разнести на 3 варианта канона (ЛАЗЕР), чтобы 750 писем не несли одну фразу. Также «ноябре–декабре» → дефис.
Правит confirm_reviews (pending) и messages.body_rendered (pending_review). Журнал _ops/gaz-lazer-1311.jsonl.
    gaz_lazer_1311.py [--primenit]"""
import io, json, os, random, sqlite3, sys
from collections import Counter
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gaz_kanon as K
ПРИМ = "--primenit" in sys.argv; random.seed(1313)
c = sqlite3.connect(r"C:\sender\sender.db", timeout=60); c.execute("PRAGMA busy_timeout=60000")
СТ = K.ЛАЗЕР[0]; сч = Counter()
жур = io.open(r"C:\sender\_ops\gaz-lazer-1311.jsonl", "a", encoding="utf-8")
for кид, body, mid in c.execute("SELECT id, body, message_id FROM confirm_reviews WHERE campaign_id=23 AND status='pending'").fetchall():
    н = body.replace("ноябре–декабре", "ноябре-декабре")
    if СТ in н:
        абз = н.split("\n\n")[1]
        if "рез" in абз.split(СТ)[0].lower(): нов = random.choice(K.ЛАЗЕР); сч["резка: вариант"] += 1
        else: нов = random.choice(K.ОХВАТ["N2"]); сч["не резка: общий охват"] += 1
        н = н.replace(СТ, нов, 1)
    if н == body: continue
    сч["правка"] += 1
    if ПРИМ:
        c.execute("UPDATE confirm_reviews SET body=? WHERE id=? AND status='pending'", (н, кид))
        if mid:
            м = c.execute("SELECT body_rendered FROM messages WHERE id=? AND status='pending_review'", (mid,)).fetchone()
            if м and м[0] and body in м[0]: c.execute("UPDATE messages SET body_rendered=? WHERE id=?", (м[0].replace(body, н), mid))
            elif м and м[0]: сч["письмо не совпало"] += 1
        жур.write(json.dumps({"karta": кид, "bylo": body, "stalo": н}, ensure_ascii=False) + "\n")
if ПРИМ: c.commit(); жур.flush(); os.fsync(жур.fileno())
print("ПРИМЕНЕНО" if ПРИМ else "сухой", dict(сч))
