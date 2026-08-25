# -*- coding: utf-8 -*-
"""Что стало с карточками, подтверждёнными 24.08 — по часам решения.

Владелец: «337 не могли уйти, они были вчера вечером уже». Значит смотреть
надо не на дату СОЗДАНИЯ письма, а на час ПОДТВЕРЖДЕНИЯ, и по каждому часу
показать судьбу: ушло / стоит в очереди / снято и чем именно.
"""
import sqlite3
from collections import Counter, defaultdict

c = sqlite3.connect(r"C:\sender\sender.db", timeout=30)
c.row_factory = sqlite3.Row

print("=== ЧАСЫ ПОДТВЕРЖДЕНИЯ 24.08 (время базы) ===")
ряды = c.execute(
    "SELECT substr(cr.decided_at,12,2) час, COALESCE(cr.decided_by,'-') кто, "
    "       cr.status st, COALESCE(m.status,'нет письма') ms, "
    "       substr(COALESCE(m.sent_at,''),1,16) когда, "
    "       COALESCE(NULLIF(m.last_error,''), cr.reason,'') почему "
    "  FROM confirm_reviews cr LEFT JOIN messages m ON m.id=cr.message_id "
    " WHERE substr(cr.decided_at,1,10)='2026-08-24'").fetchall()
по_часу = defaultdict(Counter)
кто_час = defaultdict(Counter)
for р in ряды:
    if р["ms"] == "sent":
        к = "ушло " + (р["когда"][:10] or "?")
    elif р["ms"] in ("scheduled", "sending"):
        к = "в очереди"
    elif р["st"] in ("pending", "edited"):
        к = "ждёт"
    elif р["ms"] == "failed":
        к = "сорвалось"
    else:
        к = "снято"
    по_часу[р["час"]][к] += 1
    кто_час[р["час"]][р["кто"][:22]] += 1

for ч in sorted(по_часу):
    ст = по_часу[ч]
    кто = ", ".join("%s×%d" % (к, н) for к, н in кто_час[ч].most_common(2))
    print("%s:00  всего %4d | %s   [%s]"
          % (ч, sum(ст.values()),
             "  ".join("%s %d" % (к, н) for к, н in ст.most_common()), кто))

print("\n=== ПОЧЕМУ СНЯТЫ ПОДТВЕРЖДЁННЫЕ 24.08 ===")
снятые = [р for р in ряды if р["ms"] not in ("sent", "scheduled", "sending")
          and р["st"] not in ("pending", "edited") and р["ms"] != "failed"]
print("снято всего: %d" % len(снятые))
for к, н in Counter(р["почему"][:58] for р in снятые).most_common(12):
    print("   %-58s %5d" % (к, н))
print("\nкогда сняли:")
for р in c.execute(
        "SELECT substr(m.updated_at,1,13) ч, COUNT(*) n FROM messages m "
        "  JOIN confirm_reviews cr ON cr.message_id=m.id "
        " WHERE substr(cr.decided_at,1,10)='2026-08-24' AND m.status='skipped' "
        " GROUP BY ч ORDER BY n DESC LIMIT 8"):
    print("   %s  %5d" % (р["ч"], р["n"]))
