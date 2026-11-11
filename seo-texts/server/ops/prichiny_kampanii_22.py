import sqlite3
c = sqlite3.connect("file:C:\\sender\\sender.db?mode=ro", uri=True, timeout=60)
print(c.execute("SELECT status, reason, COUNT(*) FROM confirm_reviews WHERE campaign_id=22 GROUP BY status, reason").fetchall())
