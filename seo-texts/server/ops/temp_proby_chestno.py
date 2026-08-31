# -*- coding: utf-8 -*-
"""Честный темп пробы. Прошлый замер врал из-за формата времени.

В addr_probe.ts лежит ISO с «T» и смещением: '2026-08-31T07:31:35.695344+00:00'.
SQLite datetime('now') отдаёт '2026-08-31 07:59:55' — с ПРОБЕЛОМ. При строковом
сравнении любая строка с 'T' больше строки с пробелом того же дня, поэтому
условие ts >= datetime('now','-1 hour') ловило ВСЕ сегодняшние строки.
Сравниваем, приведя обе стороны к одному виду.
"""
import sqlite3

c = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\sender.db", uri=True,
                    timeout=60)
c.row_factory = sqlite3.Row
НОРМ = "replace(substr(ts,1,19),'T',' ')"

print("=== ТЕМП РАБОТНИКА (правильное сравнение) ===")
for окно, метка in (("-15 minutes", "15 минут"), ("-1 hour", "час"),
                    ("-3 hours", "3 часа"), ("-1 day", "сутки")):
    n = c.execute("SELECT COUNT(*) FROM addr_probe WHERE source='проба'"
                  "   AND %s >= datetime('now','%s')" % (НОРМ, окно)).fetchone()[0]
    print("   за %-8s %6d проб" % (метка, n))
всего = c.execute("SELECT COUNT(*) FROM addr_probe WHERE source='проба'"
                  ).fetchone()[0]
макс = c.execute("SELECT MAX(ts) FROM addr_probe WHERE source='проба'"
                 ).fetchone()[0]
print("   всего проб работника за всё время: %d" % всего)
print("   последний вердикт в базе: %s" % макс)

print("\n=== ПО ЧАСАМ СЕГОДНЯ ===")
for r in c.execute("SELECT substr(ts,12,2) час, COUNT(*) n FROM addr_probe"
                   " WHERE source='проба' AND substr(ts,1,10)='2026-08-31'"
                   " GROUP BY час ORDER BY час"):
    print("   %s:00 UTC  %5d" % (r[0], r[1]))

print("\n=== НАША ПАРТИЯ ===")
for r in c.execute(
        "SELECT COALESCE(p.verdict,'ПРОБЫ НЕТ') в, COALESCE(p.source,'') ист,"
        "       COUNT(*) n FROM confirm_reviews cr"
        "  LEFT JOIN addr_probe p ON p.email = lower(trim(cr.email))"
        " WHERE cr.campaign_id=11 AND cr.created_at >= '2026-08-31'"
        " GROUP BY в, ист ORDER BY n DESC"):
    print("   %-16s %-12s %5d" % (r[0], r[1] or "—", r[2]))
нет = c.execute(
    "SELECT COUNT(*) FROM confirm_reviews cr"
    " LEFT JOIN addr_probe p ON p.email = lower(trim(cr.email))"
    " WHERE cr.campaign_id=11 AND cr.created_at >= '2026-08-31'"
    "   AND p.email IS NULL").fetchone()[0]
всего_п = c.execute("SELECT COUNT(*) FROM confirm_reviews"
                    " WHERE campaign_id=11 AND created_at >= '2026-08-31'"
                    ).fetchone()[0]
c.close()
print("\n=== ИТОГ ===")
print("писем партии %d: проверено %d, ждут пробы %d"
      % (всего_п, всего_п - нет, нет))
