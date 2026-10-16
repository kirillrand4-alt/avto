import sqlite3, sys
c = sqlite3.connect(r"C:\sender\sender.db")
for i, em, s, b in c.execute("SELECT id, email, subject, body FROM confirm_reviews WHERE campaign_id=? ORDER BY id DESC LIMIT ?", (int(sys.argv[1]), int(sys.argv[2]))):
    print("==== #%d %s\nТема: %s\n%s\n" % (i, em, s, b))
