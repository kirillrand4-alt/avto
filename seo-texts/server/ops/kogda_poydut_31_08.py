# -*- coding: utf-8 -*-
"""Только чтение: когда именно уйдут оставшиеся письма."""
import sqlite3
from collections import Counter
from datetime import datetime

s = sqlite3.connect("file:C:/sender/sender.db?mode=ro", uri=True)
s.row_factory = sqlite3.Row
print("=== scheduled_at ПО ЧАСАМ (UTC) ===")
c = Counter()
for р in s.execute("SELECT substr(scheduled_at,1,13) ч, COUNT(*) n FROM messages"
                   " WHERE status='scheduled' GROUP BY ч ORDER BY ч"):
    c[р["ч"]] = р["n"]
    мск = ""
    try:
        д = datetime.strptime(р["ч"], "%Y-%m-%dT%H")
        мск = " = %02d:00 мск" % ((д.hour + 3) % 24)
    except Exception:
        pass
    print("  %s  %4d%s" % (р["ч"], р["n"], мск))

print("\n=== ЧТО ПРОИСХОДИЛО (события sent по часам UTC) ===")
for р in s.execute("SELECT substr(created_at,1,13) ч, COUNT(*) n FROM events"
                   " WHERE event_type='sent' AND created_at >= '2026-08-31'"
                   " GROUP BY ч ORDER BY ч DESC LIMIT 8"):
    д = р["ч"]
    try:
        dt = datetime.strptime(д, "%Y-%m-%dT%H")
        мск = " = %02d:00 мск" % ((dt.hour + 3) % 24)
    except Exception:
        мск = ""
    print("  %s  %4d%s" % (д, р["n"], мск))

print("\n=== ИТОГ ===")
теперь = s.execute("SELECT datetime('now') n").fetchone()["n"]
print("  сейчас UTC %s (мск %s)" % (теперь, datetime.now().strftime("%H:%M")))
буд = sum(v for k, v in c.items() if k > теперь[:13])
прош = sum(v for k, v in c.items() if k <= теперь[:13])
print("  писем со временем В БУДУЩЕМ: %d" % буд)
print("  писем со временем в прошлом: %d (из них 3 снимет заслон 90 дней)" % прош)
ближ = min((k for k in c if k > теперь[:13]), default=None)
if ближ:
    print("  ближайшая партия: %s (%d писем)" % (ближ, c[ближ]))
