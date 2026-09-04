# -*- coding: utf-8 -*-
"""Починка партии 13: вернуть пометку «повтор разрешён» и поднять снятые.

Причина поломки: пометку я ставил при заведении письма, а confirm_decide
при одобрении ПЕРЕПИСЫВАЕТ поле reason тем, что ему передали (у меня
None). Пометка стёрлась, и заслон «уже писали» снял письма пачкой.
В партии вебинара этого не случилось, потому что там пометка ставилась
отдельным UPDATE уже ПОСЛЕ одобрения.

argv: проба | делать
"""
import datetime as dt
import sqlite3
import sys

ДЕЛАТЬ = (sys.argv[1] if len(sys.argv) > 1 else "проба") == "делать"
ПОМЕТКА = ("повтор разрешён: второй контакт компании, первому писали и ответа нет")

c = sqlite3.connect(r"C:\sender\sender.db")
c.row_factory = sqlite3.Row
print("=== СЕЙЧАС В ПАРТИИ 13 ===")
for р in c.execute("SELECT status, COUNT(*) k FROM messages WHERE campaign_id=13"
                   " GROUP BY status"):
    print("  письма %-14s %d" % (р["status"], р["k"]))
снятые = c.execute("SELECT COUNT(*) FROM messages WHERE campaign_id=13"
                   " AND status='skipped' AND last_error LIKE"
                   " 'auto_send:уже писали%'").fetchone()[0]
без_пометки = c.execute("SELECT COUNT(*) FROM confirm_reviews WHERE campaign_id=13"
                        " AND (reason IS NULL OR reason NOT LIKE"
                        " '%повтор разрешён%')").fetchone()[0]
print("  снято заслоном «уже писали»: %d" % снятые)
print("  решений без пометки: %d" % без_пометки)

if not ДЕЛАТЬ:
    print("\nбудет: вернуть пометку %d решениям, поднять %d писем"
          % (без_пометки, снятые))
    print("ничего не изменено (режим пробы)")
    raise SystemExit(0)

сейчас = dt.datetime.now()
n1 = c.execute("UPDATE confirm_reviews SET reason=?, updated_at=?"
               " WHERE campaign_id=13 AND (reason IS NULL OR reason NOT LIKE"
               " '%повтор разрешён%')", (ПОМЕТКА, сейчас.isoformat())).rowcount
n2 = c.execute("UPDATE messages SET status='scheduled', last_error=NULL,"
               " claimed_at=NULL, scheduled_at=?, updated_at=?"
               " WHERE campaign_id=13 AND status='skipped'"
               " AND last_error LIKE 'auto_send:уже писали%'",
               (сейчас.isoformat(), сейчас.isoformat())).rowcount
c.commit()
print("\n=== СДЕЛАНО ===")
print("  пометка возвращена решениям: %d" % n1)
print("  поднято писем из skipped: %d" % n2)
print("\n=== СТАЛО ===")
for р in c.execute("SELECT status, COUNT(*) k FROM messages WHERE campaign_id=13"
                   " GROUP BY status"):
    print("  письма %-14s %d" % (р["status"], р["k"]))
print("  решений с пометкой: %d"
      % c.execute("SELECT COUNT(*) FROM confirm_reviews WHERE campaign_id=13"
                  " AND reason LIKE '%повтор разрешён%'").fetchone()[0])
