# -*- coding: utf-8 -*-
"""Срок писем партии 13 записан московским временем, а движок сравнивает
его с UTC. Из-за трёх часов разницы письма считаются ещё не созревшими.
Переписываем срок в UTC.

argv: проба | делать
"""
import datetime as dt
import sqlite3
import sys

ДЕЛАТЬ = (sys.argv[1] if len(sys.argv) > 1 else "проба") == "делать"
c = sqlite3.connect(r"C:\sender\sender.db")
c.row_factory = sqlite3.Row
мск = dt.datetime.now()
utc = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)
print("местное %s, UTC %s" % (мск.strftime("%H:%M"), utc.strftime("%H:%M")))

созрело_utc = c.execute(
    "SELECT COUNT(*) FROM messages WHERE campaign_id=13 AND status='scheduled'"
    " AND scheduled_at<=?", (utc.isoformat(),)).fetchone()[0]
созрело_мск = c.execute(
    "SELECT COUNT(*) FROM messages WHERE campaign_id=13 AND status='scheduled'"
    " AND scheduled_at<=?", (мск.isoformat(),)).fetchone()[0]
всего = c.execute("SELECT COUNT(*) FROM messages WHERE campaign_id=13"
                  " AND status='scheduled'").fetchone()[0]
print("  писем в очереди: %d" % всего)
print("  созрели по UTC (как считает движок): %d" % созрело_utc)
print("  созрели по местному (как я думал):   %d" % созрело_мск)

for р in c.execute("SELECT substr(scheduled_at,1,13) ч, COUNT(*) k FROM messages"
                   " WHERE campaign_id=13 AND status='scheduled'"
                   " GROUP BY ч ORDER BY ч"):
    print("    срок %s: %d" % (р["ч"], р["k"]))

if not ДЕЛАТЬ:
    print("\nбудет: срок всем письмам очереди -> %s (UTC, минус час)"
          % (utc - dt.timedelta(hours=1)).isoformat(timespec="seconds"))
    print("ничего не изменено (режим пробы)")
    raise SystemExit(0)

новый = (utc - dt.timedelta(hours=1)).isoformat()
n = c.execute("UPDATE messages SET scheduled_at=?, updated_at=?"
              " WHERE campaign_id=13 AND status='scheduled'",
              (новый, utc.isoformat())).rowcount
c.commit()
print("\nсрок переписан у %d писем: %s" % (n, новый[:19]))
созрело = c.execute("SELECT COUNT(*) FROM messages WHERE campaign_id=13"
                    " AND status='scheduled' AND scheduled_at<=?",
                    (utc.isoformat(),)).fetchone()[0]
print("  теперь созрели по UTC: %d" % созрело)
