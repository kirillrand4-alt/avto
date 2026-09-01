# -*- coding: utf-8 -*-
"""Сколько писем ушло компаниям с выручкой НИЖЕ порога."""
import sqlite3
from collections import Counter

ПОРОГ = 30_000_000


def цифры(з):
    return "".join(c for c in str(з or "") if c.isdigit())


e = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\enrich.db", uri=True,
                    timeout=120)
выручка = {}
for r in e.execute("SELECT inn, revenue_rub FROM companies"):
    выручка[цифры(r[0])] = r[1]
e.close()

s = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\sender.db", uri=True,
                    timeout=120)
s.row_factory = sqlite3.Row


def разложить(ряды, метка):
    св = Counter()
    мелкие = []
    for r in ряды:
        и = цифры(r["inn"])
        v = выручка.get(и)
        if и not in выручка:
            св["нет в обогащении"] += 1
        elif v is None or int(v or 0) == 0:
            св["выручка неизвестна (0/NULL)"] += 1
        elif int(v) >= ПОРОГ:
            св["от 30 млн — по условию"] += 1
        else:
            св["МЕНЬШЕ 30 млн — не должны были"] += 1
            мелкие.append((r["company_name"], и, int(v), r["status"]))
    всего = sum(св.values())
    print("\n=== %s (всего %d) ===" % (метка, всего))
    for к, n in св.most_common():
        print("   %-34s %5d  (%.0f%%)" % (к, n, 100.0 * n / всего if всего else 0))
    return мелкие


сегодня = list(s.execute(
    "SELECT cr.inn, cr.status, r.company_name FROM confirm_reviews cr"
    "  LEFT JOIN recipients r ON r.id=cr.recipient_id"
    " WHERE cr.campaign_id=11 AND cr.created_at >= '2026-08-31'"
    "   AND cr.inn IS NOT NULL"))
мелкие = разложить(сегодня, "ПИСЬМА MEYER ЗА 31.08")

вся = list(s.execute(
    "SELECT cr.inn, cr.status, r.company_name FROM confirm_reviews cr"
    "  LEFT JOIN recipients r ON r.id=cr.recipient_id"
    " WHERE cr.campaign_id=11 AND cr.inn IS NOT NULL"))
разложить(вся, "ВСЯ КАМПАНИЯ 11")

отправлено = list(s.execute(
    "SELECT r.inn, 'sent' status, r.company_name FROM messages m"
    "  JOIN recipients r ON r.id=m.recipient_id"
    " WHERE m.campaign_id=11 AND m.sent_at IS NOT NULL AND r.inn IS NOT NULL"))
разложить(отправлено, "УЖЕ ОТПРАВЛЕНО ПО MEYER")
s.close()

print("\n=== ПРИМЕРЫ МЕЛКИХ ИЗ СЕГОДНЯШНИХ ===")
мелкие.sort(key=lambda x: x[2])
for имя, и, v, ст in мелкие[:12]:
    print("   %-34s ИНН %s  выручка %8.1f млн  карточка %s"
          % (str(имя)[:34], и, v / 1e6, ст))
print("\n=== ИТОГ ===")
print("писем сегодняшней партии компаниям меньше 30 млн: %d" % len(мелкие))
