# -*- coding: utf-8 -*-
"""Протолкнуть письма, снятые заслоном «уже писали».

База тёплая: человек сам зарегистрировался на наш вебинар. Заслон снял их
не за письмо ЭТОМУ человеку, а за письмо КОЛЛЕГЕ в той же компании -
проверено, ни на один из этих адресов мы раньше не писали.

Пользуемся штатной пометкой самого движка: если в reason решения стоит
«повтор разрешён», заслон сверяет только АДРЕС и не смотрит на ИНН.
Написана она была под прошлый вебинар 28.08. Правило «тому же адресу
дважды не пишем никогда» остаётся в силе.

argv: проба | делать
"""
import datetime as dt
import sqlite3
import sys

ДЕЛАТЬ = (sys.argv[1] if len(sys.argv) > 1 else "проба") == "делать"
ПОМЕТКА = "повтор разрешён: тёплая база вебинара, решение владельца 02.09"
СРОК = dt.datetime.now().replace(hour=4, minute=30, second=0, microsecond=0)

c = sqlite3.connect(r"C:\sender\sender.db")
c.row_factory = sqlite3.Row

снятые = list(c.execute(
    "SELECT m.id, cr.id AS rid, r.email FROM messages m"
    " JOIN recipients r ON r.id=m.recipient_id"
    " JOIN confirm_reviews cr ON cr.message_id=m.id"
    " WHERE m.campaign_id=12 AND m.status='skipped'"
    " AND m.last_error LIKE 'auto_send:уже писали%'"))
всего_ревью = c.execute("SELECT COUNT(*) FROM confirm_reviews"
                        " WHERE campaign_id=12").fetchone()[0]
print("снятых заслоном: %d" % len(снятые))
print("решений кампании 12 всего: %d (пометку ставим всем, чтобы заслон не"
      " срезал и остальных)" % всего_ревью)

if not ДЕЛАТЬ:
    print("ничего не изменено (режим пробы)")
    raise SystemExit(0)

сейчас = dt.datetime.now().isoformat()
n1 = c.execute("UPDATE confirm_reviews SET reason=?, updated_at=?"
               " WHERE campaign_id=12 AND (reason IS NULL OR reason NOT LIKE"
               " '%повтор разрешён%')", (ПОМЕТКА, сейчас)).rowcount
ид = [р["id"] for р in снятые]
n2 = 0
if ид:
    впис = ",".join("?" * len(ид))
    n2 = c.execute("UPDATE messages SET status='scheduled', scheduled_at=?,"
                   " claimed_at=NULL, last_error=NULL, updated_at=?"
                   " WHERE id IN (%s) AND status='skipped'" % впис,
                   [СРОК.isoformat(), сейчас] + ид).rowcount
c.commit()
print("пометка проставлена решениям: %d" % n1)
print("возвращено в очередь писем: %d, срок %s" % (n2, СРОК.strftime("%H:%M")))

print("\n=== ПРОВЕРКА ===")
for р in c.execute("SELECT status, COUNT(*) k FROM messages WHERE campaign_id=12"
                   " GROUP BY status"):
    print("  %-14s %d" % (р["status"], р["k"]))
print("  решений с пометкой: %d"
      % c.execute("SELECT COUNT(*) FROM confirm_reviews WHERE campaign_id=12"
                  " AND reason LIKE '%повтор разрешён%'").fetchone()[0])
