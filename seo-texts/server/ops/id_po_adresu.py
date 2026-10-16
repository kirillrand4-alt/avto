import sqlite3, sys
c = sqlite3.connect(r"C:\sender\sender.db")
print(c.execute("SELECT m.id, m.status, m.mailbox_id, m.subject, m.sent_at FROM messages m JOIN recipients r ON r.id=m.recipient_id WHERE lower(r.email)=? ORDER BY m.id DESC LIMIT 3", (sys.argv[1].lower(),)).fetchall())
