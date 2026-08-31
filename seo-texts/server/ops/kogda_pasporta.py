# -*- coding: utf-8 -*-
"""Когда появились паспорта у компаний, которым сейчас пишем."""
import json
import sqlite3
from collections import Counter

s = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\sender.db", uri=True,
                    timeout=60)
s.row_factory = sqlite3.Row
инн_прогона = []
for r in s.execute("SELECT DISTINCT inn FROM confirm_reviews"
                   " WHERE campaign_id=11 AND created_at >= datetime('now','-3 hour')"
                   "   AND inn IS NOT NULL"):
    и = str(r["inn"] or "")
    if и:
        инн_прогона.append(и)
s.close()
print("компаний в сегодняшнем прогоне: %d" % len(инн_прогона))

e = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\enrich.db", uri=True,
                    timeout=90)
e.row_factory = sqlite3.Row
даты = Counter()
нет = 0
поля = Counter()
for i in range(0, len(инн_прогона), 400):
    часть = инн_прогона[i:i + 400]
    нашлись = set()
    for r in e.execute("SELECT inn, ts, facts_json FROM site_facts"
                       " WHERE inn IN (%s)" % ",".join("?" * len(часть)), часть):
        нашлись.add(str(r["inn"]))
        даты[str(r["ts"] or "")[:10]] += 1
        try:
            поля[len(json.loads(r["facts_json"] or "{}") or {})] += 1
        except Exception:                                     # noqa: BLE001
            pass
    нет += len(часть) - len(нашлись)
e.close()

print("\n=== ПАСПОРТ САЙТА У НИХ ===")
print("   есть: %d, нет: %d" % (sum(даты.values()), нет))
print("\n   когда собран паспорт:")
for д, n in sorted(даты.items(), reverse=True)[:10]:
    print("      %s  %5d" % (д, n))
print("\n   сколько полей в паспорте:")
for к, n in sorted(поля.items(), reverse=True)[:8]:
    print("      %2d полей  %5d" % (к, n))

print("\n=== ИТОГ ===")
всего = sum(даты.values()) + нет
print("паспорт есть у %d из %d компаний прогона (%.0f%%)"
      % (sum(даты.values()), всего,
         100.0 * sum(даты.values()) / всего if всего else 0))
свежие = sum(n for д, n in даты.items() if д >= "2026-08-30")
print("из них собраны 30–31.08: %d" % свежие)
