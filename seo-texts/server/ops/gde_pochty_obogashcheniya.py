# -*- coding: utf-8 -*-
"""В какой из двух enrich.db лежат наши адреса."""
import sqlite3

c = sqlite3.connect(r"C:\sender\sender.db", timeout=60)
приг = [r[0] for r in c.execute(
    "SELECT email FROM addr_probe WHERE verdict IN ('нет ящика','нет MX')")]
c.close()
print("приговоров: %d" % len(приг))
образцы = приг[:400]

for п in (r"C:\sender\enrich.db", r"C:\sender\server\enrich.db"):
    print("")
    print("=== %s ===" % п)
    try:
        o = sqlite3.connect("file:%s?mode=ro" % п, uri=True, timeout=20)
        всего = o.execute("SELECT COUNT(*) FROM emails").fetchone()[0]
        скол = [r[1] for r in o.execute("PRAGMA table_info(emails)")]
        есть = 0
        for а in образцы:
            if o.execute("SELECT 1 FROM emails WHERE lower(email)=? LIMIT 1",
                         (а,)).fetchone():
                есть += 1
        свердиктом = 0
        if "probe_verdict" in скол:
            свердиктом = o.execute(
                "SELECT COUNT(*) FROM emails WHERE probe_verdict IS NOT NULL "
                "AND probe_verdict<>''").fetchone()[0]
        o.close()
        print("   строк в emails: %d | колонок: %d | с вердиктом: %d"
              % (всего, len(скол), свердиктом))
        print("   из 400 приговорённых нашлось: %d" % есть)
    except Exception as ex:                                   # noqa: BLE001
        print("   не открылась: %s" % str(ex)[:120])
