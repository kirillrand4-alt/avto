# -*- coding: utf-8 -*-
"""Снять паузу с мейеровских ящиков, у которых своих отказов нет.

Их остановил рубеж направления из-за пяти отказов одного козлова. Козлова
НЕ трогаем: владелец 25.08 — «не надо его возвращать, если он спам
постоянно ловит». Каждому ящику смотрим его СОБСТВЕННЫЙ счёт отказов за
сутки, и если он не ноль — ящик остаётся стоять.
"""
import sqlite3
import sys

ДЕЛАТЬ = "primenit" in sys.argv[1:]
ОСТАВИТЬ = {"a.kozlov@zernosort.ru"}
c = sqlite3.connect(r"C:\sender\sender.db", timeout=30)
c.row_factory = sqlite3.Row
кол = [р[1] for р in c.execute("PRAGMA table_info(events)")]
поле = "event_type" if "event_type" in кол else "type"
время = "event_ts" if "event_ts" in кол else "created_at"
print("events: поле типа «%s», поле времени «%s»" % (поле, время))

снять = []
for р in c.execute("SELECT mailbox_id, pause_reason FROM mailbox_state "
                   " WHERE paused=1"):
    я = р["mailbox_id"]
    свои = c.execute(
        "SELECT COUNT(*) FROM events WHERE mailbox_id=? AND %s='reject_spam' "
        "   AND substr(%s,1,10)=date('now')" % (поле, время), (я,)).fetchone()[0]
    метка = ("ОСТАВИТЬ (владелец)" if я in ОСТАВИТЬ
             else ("ОСТАВИТЬ (свои отказы)" if свои else "снять паузу"))
    print("   %-38s своих отказов сегодня %2d → %s" % (я, свои, метка))
    if метка == "снять паузу":
        снять.append(я)

print("\nк снятию: %d" % len(снять))
if not ДЕЛАТЬ:
    print("вхолостую. Применить — primenit")
    raise SystemExit(0)
for я in снять:
    c.execute("UPDATE mailbox_state SET paused=0, pause_reason=NULL, "
              "       updated_at=datetime('now') WHERE mailbox_id=?", (я,))
c.commit()
print("снято пауз: %d" % len(снять))
for р in c.execute("SELECT mailbox_id, paused, COALESCE(pause_reason,'') пр "
                   "  FROM mailbox_state WHERE mailbox_id LIKE '%sort%' "
                   "    OR mailbox_id LIKE '%zerno%'"):
    print("   %-38s пауза %s %s" % (р["mailbox_id"], р["paused"], р["пр"][:44]))
