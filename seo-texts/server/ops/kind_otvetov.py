import sqlite3
c = sqlite3.connect(r"C:\sender\sender.db", timeout=60)
for r in c.execute("SELECT cr.kind, m.status, COUNT(*), MIN(substr(COALESCE(cr.edited_body, cr.body),1,90)) FROM confirm_reviews cr JOIN messages m ON m.id=cr.message_id GROUP BY 1,2"): print(r)
print(c.execute("SELECT event_type, COUNT(*) FROM events WHERE event_type LIKE '%reply%' OR event_type LIKE '%ruch%' GROUP BY 1").fetchall())
