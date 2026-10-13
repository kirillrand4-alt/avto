# -*- coding: utf-8 -*-
"""Что лежит в enrich.companies: division, is_competitor, nash_priznak, nash_dokaz."""
import sqlite3
from collections import Counter
cx = sqlite3.connect(r"C:\sender\enrich.db", timeout=30)
print("всего компаний: %d" % cx.execute("SELECT count(*) FROM companies").fetchone()[0])
for к in ("division", "is_competitor", "nash_priznak"):
    print("%s: %s" % (к, Counter(str(р[0])[:40] for р in cx.execute("SELECT %s FROM companies" % к)).most_common(8)))
for р in cx.execute("SELECT inn, name, nash_priznak, nash_dokaz FROM companies WHERE coalesce(nash_priznak,'')<>'' LIMIT 4"):
    print("   %s | %s | %s | %s" % (р[0], str(р[1])[:30], str(р[2])[:40], str(р[3])[:120]))
c = sqlite3.connect(r"C:\sender\sender.db", timeout=30)
print("target_verdicts: %s" % Counter(р[0] for р in c.execute("SELECT verdict FROM target_verdicts")).most_common())
print("=== КОЛОНКИ НАШ ===")
