# -*- coding: utf-8 -*-
"""Часовые зоны получателей партии против их реального региона."""
import sys
from collections import Counter
sys.path.insert(0, r"C:\sender")
from sender.store import Store                                  # noqa: E402

ИСТОЧНИКИ = ("чеко-агро-2026", "чеко-агро-2026-второй")
store = Store(r"C:\sender\sender.db")
зоны = Counter()
регионы = Counter()
пары = Counter()
with store._lock:
    for р in store._conn.execute(
            "SELECT inn, tz, region, source FROM recipients WHERE source IN (?,?)",
            ИСТОЧНИКИ):
        з = str(р["tz"] or "нет")
        рег = str(р["region"] or "?")
        зоны[з] += 1
        регионы[рег] += 1
        пары[(рег, з)] += 1
    # для сравнения: вся база
    всего = Counter()
    for р in store._conn.execute("SELECT tz, COUNT(*) c FROM recipients GROUP BY tz"):
        всего[str(р["tz"] or "нет")] = int(р["c"])

print("--- регионы партии (топ-15) ---")
for к, в in регионы.most_common(15):
    print("   %-26s %5d" % (к, в))
print("")
print("--- часовые зоны во ВСЕЙ базе ---")
for к, в in всего.most_common(8):
    print("   %-26s %6d" % (к, в))
print("")
print("=" * 74)
print("=== ЧАСОВЫЕ ЗОНЫ ПАРТИИ ===")
for к, в in зоны.most_common():
    print("   %-26s %5d" % (к, в))
дальние = sum(в for (рег, _з), в in пары.items()
              if any(s in рег for s in ("Алтайский", "Новосибир", "Омск",
                                        "Красноярск", "Томск", "Кемеров",
                                        "Иркут", "Бурят", "Забайкал",
                                        "Хакас", "Тыва", "Якут", "Амур",
                                        "Примор", "Хабаров", "Свердлов",
                                        "Челябин", "Тюмен", "Курган",
                                        "Оренбург", "Пермск", "Башкорт",
                                        "Удмурт", "Самар", "Саратов",
                                        "Ульянов", "Астрахан", "Ханты",
                                        "Ямало")))
print("из них физически НЕ в московском времени: %d" % дальние)
