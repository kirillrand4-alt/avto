# -*- coding: utf-8 -*-
"""Только чтение: ответы сегодня против вчера, с поправкой на объём."""
import sqlite3
from datetime import datetime, timezone

s = sqlite3.connect("file:C:/sender/sender.db?mode=ro", uri=True)
s.row_factory = sqlite3.Row
print("=== ОТПРАВЛЕНО И ОТВЕТОВ ПО ДНЯМ ===")
print("  %-12s %7s %7s %10s %9s" % ("день", "ушло", "reply", "reply_auto", "доля"))
for р in s.execute(
        "SELECT substr(created_at,1,10) д,"
        " SUM(CASE WHEN event_type='sent' THEN 1 ELSE 0 END) ушло,"
        " SUM(CASE WHEN event_type='reply' THEN 1 ELSE 0 END) rep,"
        " SUM(CASE WHEN event_type='reply_auto' THEN 1 ELSE 0 END) auto"
        " FROM events WHERE created_at >= '2026-08-24'"
        " GROUP BY д ORDER BY д"):
    у = р["ушло"] or 0
    print("  %-12s %7d %7d %10d %8.2f%%"
          % (р["д"], у, р["rep"] or 0, р["auto"] or 0,
             100.0 * (р["rep"] or 0) / max(1, у)))

print("\n=== КОГДА ПРИХОДЯТ ОТВЕТЫ ОТНОСИТЕЛЬНО ОТПРАВКИ ===")
for р in s.execute(
        "SELECT substr(e.created_at,1,10) д, COUNT(*) n,"
        " AVG(julianday(e.created_at) - julianday(m.sent_at)) * 24 часов"
        " FROM events e JOIN messages m ON m.id=e.message_id"
        " WHERE e.event_type='reply' AND m.sent_at IS NOT NULL"
        " AND e.created_at >= '2026-08-24' GROUP BY д ORDER BY д"):
    print("  %s  ответов %3d, средняя задержка %.1f ч"
          % (р["д"], р["n"], р["часов"] or 0))

print("\n=== ИТОГ ===")
СЕГ = datetime.now(timezone.utc).strftime("%Y-%m-%dT00:00:00")
for т in ("reply", "reply_auto"):
    n = s.execute("SELECT COUNT(*) n FROM events WHERE event_type=? AND created_at >= ?",
                  (т, СЕГ)).fetchone()["n"]
    print("  сегодня %-12s %d" % (т, n))
у = s.execute("SELECT COUNT(*) n FROM events WHERE event_type='sent' AND created_at >= ?",
              (СЕГ,)).fetchone()["n"]
print("  сегодня отправлено: %d" % у)
print("  вчера отправлено  : %d"
      % s.execute("SELECT COUNT(*) n FROM events WHERE event_type='sent'"
                  " AND created_at >= '2026-08-31T00' AND created_at < '2026-09-01T00'"
                  ).fetchone()["n"])
print("  сейчас мск %s — рабочий день ещё не кончился"
      % datetime.now().strftime("%H:%M"))
