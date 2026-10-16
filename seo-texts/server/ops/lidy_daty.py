import sqlite3, sys
c = sqlite3.connect(r"C:\sender\sender.db")
for lid in sys.argv[1].split(","):
    r = c.execute("SELECT id, company_name, substr(created_at,1,10), substr(updated_at,1,10), status, reply_kind FROM leads WHERE id=?", (int(lid),)).fetchone()
    print(r)
