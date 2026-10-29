# -*- coding: utf-8 -*-
"""Дубли карточек: у одного получателя/адреса несколько pending в кампании.
    dubli_kartochek.py <campaign_id> [--snyat]  (снимает лишние, оставляет самую раннюю)"""
import sqlite3
import sys
from datetime import datetime
c = sqlite3.connect(r"C:\sender\sender.db", timeout=60)
cid = int(sys.argv[1])
ряды = c.execute("SELECT lower(email), GROUP_CONCAT(id), COUNT(*) FROM confirm_reviews WHERE status='pending' AND campaign_id=? "
                 "GROUP BY lower(email) HAVING COUNT(*)>1", (cid,)).fetchall()
print("адресов с несколькими pending:", len(ряды), "| лишних карточек:", sum(r[2] - 1 for r in ряды))
for r in ряды[:5]:
    print("  ", r)
if "--snyat" in sys.argv:
    т = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S")
    n = 0
    with c:
        for em, ids, k in ряды:
            for i in sorted(int(x) for x in ids.split(","))[1:]:
                mid = c.execute("SELECT message_id FROM confirm_reviews WHERE id=?", (i,)).fetchone()[0]
                c.execute("UPDATE confirm_reviews SET status='skipped', reason='дубль карточки (двойной запуск починки 29.10)', decided_at=?, updated_at=? WHERE id=?", (т, т, i))
                if mid:
                    c.execute("UPDATE messages SET status='skipped', last_error='дубль карточки' WHERE id=? AND status IN ('pending_review','scheduled') "
                              "AND NOT EXISTS (SELECT 1 FROM confirm_reviews WHERE message_id=? AND status='pending')", (mid, mid))
                n += 1
    print("снято дублей:", n)
