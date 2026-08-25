import sqlite3
c = sqlite3.connect(r"C:\sender\sender.db")
for r in c.execute("SELECT tz, COUNT(*) n FROM recipients GROUP BY tz ORDER BY n DESC LIMIT 6"):
    print("   tz=%-20s %d" % (r[0], r[1]))
for r in c.execute("SELECT segment, COUNT(*) n FROM recipients GROUP BY segment ORDER BY n DESC LIMIT 8"):
    print("   segment=%-24s %d" % (r[0], r[1]))
for r in c.execute("SELECT source, COUNT(*) n FROM recipients GROUP BY source ORDER BY n DESC LIMIT 8"):
    print("   source=%-24s %d" % (r[0], r[1]))
