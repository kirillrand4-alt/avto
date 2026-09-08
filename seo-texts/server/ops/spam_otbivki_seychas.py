# -*- coding: utf-8 -*-
"""Отбивки «подозрение на спам»: сколько, с каких ящиков, с какого момента."""
import sys
from collections import Counter
sys.path.insert(0, r"C:\sender")
from sender.store import Store                                  # noqa: E402

store = Store(r"C:\sender\sender.db")
кол = []
with store._lock:
    кол = [c[1] for c in store._conn.execute("PRAGMA table_info(events)")]
    поле_вр = next((c for c in ("ts", "created_at", "occurred_at", "at",
                                "event_ts") if c in кол), None)
    if поле_вр is None:
        строки = store._conn.execute(
            "SELECT * FROM events ORDER BY rowid DESC LIMIT 4000").fetchall()
    else:
        строки = store._conn.execute(
            "SELECT * FROM events WHERE %s >= datetime('now','-6 hours') "
            " ORDER BY %s DESC LIMIT 4000" % (поле_вр, поле_вр)).fetchall()
print("колонки events: %s" % ", ".join(кол))

спам = []
всего = Counter()
for р in строки:
    текст = " ".join(str(р[c] or "") for c in кол
                     if isinstance(р[c], str))
    поле_тип = next((c for c in ("type", "kind", "event_type", "name")
                     if c in кол), None)
    тип = str(р[поле_тип]) if поле_тип else "?"
    всего[тип] += 1
    if "спам" in текст.lower() or "spam" in текст.lower():
        спам.append((str(р[поле_вр] if поле_вр else ""), тип, текст))

по_часам = Counter(т[:13] for т, _т, _x in спам)
по_ящику = Counter()
по_домену = Counter()
for _т, _тип, текст in спам:
    for сл in текст.split():
        if "@" in сл and сл.count("@") == 1:
            лок, дом = сл.strip("<>,;\"'").split("@")
            if any(d in дом for d in ("optical-sort", "sorting-syst", "inspection",
                                      "zernosort", "sort-systems", "food-sort",
                                      "optic-sort", "rentgen")):
                по_ящику[сл.strip("<>,;\"'")] += 1
            else:
                по_домену[дом.strip("<>,;\"'.")] += 1

print("")
print("--- спам-отбивки по часам ---")
for к in sorted(по_часам):
    print("   %s  %4d" % (к, по_часам[к]))
print("")
print("--- с каких наших ящиков ---")
for к, в in по_ящику.most_common(10):
    print("   %-42s %4d" % (к, в))
print("")
print("--- домены получателей ---")
for к, в in по_домену.most_common(8):
    print("   %-28s %4d" % (к, в))
print("")
print("=" * 74)
print("=== СПАМ-ОТБИВКИ ЗА 6 ЧАСОВ ===")
print("всего событий за 6 часов: %d; из них про спам: %d"
      % (len(строки), len(спам)))
for к, в in всего.most_common(8):
    print("   событие %-28s %5d" % (к, в))
