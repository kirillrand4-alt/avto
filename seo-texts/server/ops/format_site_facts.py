# -*- coding: utf-8 -*-
"""Формат enrich.db/site_facts: схема, ключи паспорта, пример, покрытие."""
import json
import sqlite3
from collections import Counter

cx = sqlite3.connect(r"C:\sender\enrich.db", timeout=60)
cx.row_factory = sqlite3.Row
print("схема: %s" % [(р["name"], р["type"]) for р in
                     cx.execute("PRAGMA table_info(site_facts)")])
всего = cx.execute("SELECT COUNT(*) FROM site_facts").fetchone()[0]
print("строк: %d" % всего)
ключи = Counter()
типы = {}
пример = None
for р in cx.execute("SELECT inn, facts_json, sources_json FROM site_facts "
                    "ORDER BY rowid DESC LIMIT 3000"):
    try:
        д = json.loads(р["facts_json"] or "{}")
    except Exception:  # noqa: BLE001
        continue
    if isinstance(д, dict):
        for к, v in д.items():
            ключи[к] += 1
            типы.setdefault(к, type(v).__name__)
        if пример is None and len(д) >= 5:
            пример = (р["inn"], д, р["sources_json"])
print("")
print("--- ключи паспорта (из последних 3000) ---")
for к, n in ключи.most_common(30):
    print("   %-26s %5d  %s" % (к, n, типы.get(к)))
if пример:
    print("")
    print("--- пример ---")
    print("   inn %s" % пример[0])
    print("   " + json.dumps(пример[1], ensure_ascii=False)[:900])
    print("   sources: " + str(пример[2])[:300])
print("")
print("=== ФОРМАТ SITE_FACTS ===")
