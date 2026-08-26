# -*- coding: utf-8 -*-
"""Почему UPDATE в обогащении не находит строк: проверяем руками."""
import sqlite3

c = sqlite3.connect(r"C:\sender\sender.db", timeout=60)
адреса = [r[0] for r in c.execute(
    "SELECT email FROM addr_probe WHERE verdict IN ('нет ящика','нет MX') LIMIT 5")]
c.close()
print("образцы: %s" % адреса)

o = sqlite3.connect(r"C:\sender\enrich.db", timeout=60)
for а in адреса:
    есть = o.execute("SELECT COUNT(*) FROM emails WHERE lower(email)=?",
                     (а,)).fetchone()[0]
    print("   %-40s строк в emails: %d" % (а, есть))
кол = [r[1] for r in o.execute("PRAGMA table_info(emails)")]
print("колонки emails: %s" % ", ".join(кол))
if адреса:
    cur = o.execute("UPDATE emails SET probe_verdict='нет ящика' WHERE lower(email)=?",
                    (адреса[0],))
    print("пробный UPDATE rowcount=%d" % cur.rowcount)
    o.rollback()
o.close()
