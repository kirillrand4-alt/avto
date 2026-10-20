# -*- coding: utf-8 -*-
"""Где сейчас письма (владелец 20.10: «почему я вижу только 395?»):
карточки на подтверждении по кампаниям; письма кампании 17 (КЦ-1 август) по
статусам; годные из журнала генерации без карточки."""
import io
import json
import sqlite3
from collections import Counter

c = sqlite3.connect(r"C:\sender\sender.db")
кам = {r[0]: r[1] for r in c.execute("SELECT id, name FROM campaigns")}
print("НА ПОДТВЕРЖДЕНИИ (карточки pending) по кампаниям:")
for cid, n in c.execute("SELECT campaign_id, COUNT(*) FROM confirm_reviews WHERE status='pending' "
                        "AND COALESCE(kind,'outbound')!='reply' GROUP BY campaign_id ORDER BY 2 DESC"):
    print("  %-32s %5d" % (кам.get(cid, cid), n))
print("  ответы клиентам (reply):", c.execute("SELECT COUNT(*) FROM confirm_reviews WHERE status='pending' AND kind='reply'").fetchone()[0])
print("\nКЦ-1 август (кампания 17), письма по статусам:")
for st, n in c.execute("SELECT status, COUNT(*) FROM messages WHERE campaign_id=17 GROUP BY status ORDER BY 2 DESC"):
    print("  %-16s %5d" % (st, n))
print("  карточки по статусам:", dict(c.execute("SELECT status, COUNT(*) FROM confirm_reviews WHERE campaign_id=17 GROUP BY status").fetchall()))
ok = set()
for s in io.open(r"C:\sender\_ops\gen-kc1-avgust.jsonl", encoding="utf-8"):
    z = json.loads(s)
    if z.get("этап") == "итог" and z.get("ok", z.get("ок")):
        ok.add(z.get("review_id"))
print("годных в журнале генерации:", len(ok))
skip = Counter(str(r[0] or "")[:60] for r in c.execute(
    "SELECT reason FROM confirm_reviews WHERE campaign_id=17 AND status='skipped'"))
print("причины skipped у карточек 17:", skip.most_common(6))
