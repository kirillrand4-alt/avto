import sqlite3, sys
c = sqlite3.connect(r"C:\sender\sender.db")
print(c.execute("SELECT id, status, reason, email, subject FROM confirm_reviews WHERE id=?", (int(sys.argv[1]),)).fetchone())
