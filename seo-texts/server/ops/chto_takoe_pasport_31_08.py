# -*- coding: utf-8 -*-
"""Только чтение: что лежит в паспорте сайта и насколько он заполнен."""
import json
import sqlite3
from collections import Counter

e = sqlite3.connect("file:C:/sender/enrich.db?mode=ro", uri=True)
e.row_factory = sqlite3.Row
s = sqlite3.connect("file:C:/sender/sender.db?mode=ro", uri=True)
s.row_factory = sqlite3.Row

меyer = {str(р["inn"]) for р in s.execute(
    "SELECT DISTINCT inn FROM recipients WHERE segment='meyer' AND inn IS NOT NULL")}

ключи = Counter()
заполнено = Counter()
распр = Counter()
всего = 0
богатый = None
for р in e.execute("SELECT inn, facts_json, site FROM site_facts"):
    if str(р["inn"]) not in меyer:
        continue
    try:
        f = json.loads(р["facts_json"] or "{}")
    except Exception:
        continue
    всего += 1
    b = 0
    for k, v in f.items():
        ключи[k] += 1
        if v not in (None, "", [], {}, "нет"):
            заполнено[k] += 1
            b += 1
    распр[b] += 1
    if b >= 14 and богатый is None:
        богатый = (р["inn"], р["site"], f)

print("=== ВСЕ ПОЛЯ ПАСПОРТА (%d карточек сегмента meyer) ===" % всего)
print("  %-24s %8s %8s" % ("поле", "есть", "непусто"))
for k, n in ключи.most_common():
    print("  %-24s %8d %7d (%3.0f%%)" % (k, n, заполнено[k], 100.0 * заполнено[k] / max(1, n)))

print("\n=== СКОЛЬКО БЛОКОВ ЗАПОЛНЕНО ===")
for b in sorted(распр):
    print("  %2d блоков: %6d карточек" % (b, распр[b]))
пуст = распр.get(0, 0)
print("  ПУСТЫХ (0 блоков): %d — их я и не считал за паспорт" % пуст)

print("\n=== ЖИВОЙ ПРИМЕР БОГАТОГО ПАСПОРТА ===")
if богатый:
    inn, site, f = богатый
    print("  ИНН %s, сайт %s" % (inn, site))
    for k, v in f.items():
        if v in (None, "", [], {}, "нет"):
            continue
        t = ", ".join(str(x) for x in v) if isinstance(v, list) else str(v)
        print("    %-22s %s" % (k, t[:110] + ("…" if len(t) > 110 else "")))

print("\n=== ИТОГ ===")
print("  полей в паспорте: %d" % len(ключи))
print("  «есть паспорт» у меня = хотя бы ОДНО непустое поле")
непустых = всего - пуст
print("  карточек meyer: %d, из них с непустым паспортом %d (%.1f%%)"
      % (всего, непустых, 100.0 * непустых / max(1, всего)))
