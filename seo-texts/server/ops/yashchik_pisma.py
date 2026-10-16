import sqlite3, sys
c = sqlite3.connect(r"C:\sender\sender.db")
print(c.execute("SELECT m.id, m.mailbox_id, m.sent_at, m.subject FROM messages m WHERE m.recipient_id=? ORDER BY id DESC LIMIT 3", (int(sys.argv[1]),)).fetchall())
import io
т = io.open(r"C:\sender\logs\inbox_poll.log", encoding="utf-8", errors="replace").read()
print(т[-1500:])
