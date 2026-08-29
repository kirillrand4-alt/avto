# -*- coding: utf-8 -*-
"""Что именно пишется в enrich.db прямо сейчас: замер таблиц дважды."""
import sqlite3, time
ТАБЛИЦЫ = ("companies", "stage_log", "emails", "site_facts", "site_text",
           "signals", "requisites", "seen_news", "qc_site", "smtp_domains")


def снимок():
    c = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\enrich.db", uri=True,
                        timeout=20)
    из = {}
    for т in ТАБЛИЦЫ:
        try:
            из[т] = c.execute("SELECT COUNT(*) FROM %s" % т).fetchone()[0]
        except Exception:
            из[т] = None
    c.close()
    return из


a = снимок()
time.sleep(30)
b = снимок()
print("%-16s %12s %12s %10s" % ("таблица", "было", "стало", "прирост"))
двигалось = False
for т in ТАБЛИЦЫ:
    if a[т] is None:
        continue
    d = b[т] - a[т]
    if d:
        двигалось = True
    print("%-16s %12d %12d %10s" % (т, a[т], b[т], ("+%d" % d) if d else "—"))
print("\nза 30 секунд %s" % ("что-то писалось" if двигалось
                             else "НИ ОДНА из этих таблиц не росла"))
