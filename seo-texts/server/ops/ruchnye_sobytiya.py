import sqlite3
c = sqlite3.connect(r"C:\sender\sender.db")
print(c.execute("SELECT event_type, COUNT(*) FROM events WHERE event_type LIKE '%reply_sent%' OR event_type LIKE '%manual%' OR event_type LIKE '%ruch%' GROUP BY 1").fetchall())
for r in c.execute("SELECT event_type, substr(detail_json,1,300) FROM events WHERE detail_json LIKE '%krohapit%' ORDER BY id DESC LIMIT 6"): print(r)
