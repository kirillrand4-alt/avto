# -*- coding: utf-8 -*-
"""Разведка: сколько адресов на домене компании остаётся в запасе."""
import sqlite3

for бд, таблы in ((r"C:\sender\sender.db", ("recipients", "messages", "suppression")),
                  (r"C:\sender\enrich.db", ("emails",))):
    c = sqlite3.connect("file:%s?mode=ro" % бд, uri=True, timeout=60)
    for т in таблы:
        try:
            кол = [r[1] for r in c.execute("PRAGMA table_info(%s)" % т)]
        except Exception as e:                                 # noqa: BLE001
            print("%s.%s: %s" % (бд, т, e)); continue
        n = c.execute("SELECT COUNT(*) FROM %s" % т).fetchone()[0]
        print("%s.%s (%d строк):\n   %s" % (бд.split("\\")[-1], т, n, ", ".join(кол)))
    c.close()

c = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\sender.db", uri=True, timeout=60)
print("")
print("статусы messages:", dict(c.execute(
    "SELECT status, COUNT(*) FROM messages GROUP BY 1").fetchall()))
print("типы events:", dict(c.execute(
    "SELECT event_type, COUNT(*) FROM events GROUP BY 1 ORDER BY 2 DESC LIMIT 15").fetchall()))
c.close()

e = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\enrich.db", uri=True, timeout=60)
print("")
print("вердикты emails:", dict(e.execute(
    "SELECT COALESCE(probe_verdict,'—'), COUNT(*) FROM emails GROUP BY 1").fetchall()))
print("компаний в emails:", e.execute(
    "SELECT COUNT(DISTINCT inn) FROM emails").fetchone()[0])
e.close()
