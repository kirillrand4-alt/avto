import sqlite3, sys
c = sqlite3.connect(r"C:\sender\sender.db", timeout=60)
for r in c.execute("SELECT cr.id, cr.status, cr.campaign_id, m.id, m.status, m.mailbox_id, cr.email, cr.panel_json FROM confirm_reviews cr LEFT JOIN messages m ON m.id=cr.message_id WHERE cr.subject LIKE ? ORDER BY cr.id DESC LIMIT 5", ("%" + sys.argv[1] + "%",)):
    print(r[:7]); pj = r[7] or ""
    i = pj.find("division"); print("   ", pj[max(0, i-80):i+200] if i >= 0 else pj[:300])
print("ящики Meyer-кампании 14 у живых писем:", c.execute("SELECT mailbox_id, COUNT(*) FROM messages WHERE campaign_id=14 AND status IN ('pending_review','scheduled') GROUP BY 1 ORDER BY 2 DESC LIMIT 8").fetchall())
