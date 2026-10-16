import sqlite3
c = sqlite3.connect(r"C:\sender\sender.db", timeout=60)
for r in c.execute("SELECT ca.id, ca.name, m.status, COUNT(*) FROM messages m JOIN campaigns ca ON ca.id=m.campaign_id "
                   "WHERE m.status IN ('pending_review','approved','scheduled','sending') GROUP BY 1,3 ORDER BY 1"):
    print(r)
print("ящики КЦ на паузе:", c.execute("SELECT COUNT(*) FROM mailbox_state WHERE paused=1 AND pause_reason LIKE '%kc%'").fetchone())
