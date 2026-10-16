import sqlite3, sys
c = sqlite3.connect(r"C:\sender\sender.db")
s, b = c.execute("SELECT subject, body_rendered FROM messages WHERE id=?", (int(sys.argv[1]),)).fetchone()
print(s); print(b)
