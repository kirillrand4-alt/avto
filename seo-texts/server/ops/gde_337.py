# -*- coding: utf-8 -*-
"""Где именно те 337 писем, что владелец подтвердил 24.08.

Их пометил возврат 25.08 своей причиной, так что когорта опознаётся точно,
а не по дате. Отдельно — общий счёт очереди отправки на сейчас.
"""
import sqlite3
from collections import Counter

c = sqlite3.connect(r"C:\sender\sender.db", timeout=30)
c.row_factory = sqlite3.Row
когорта = c.execute(
    "SELECT cr.id, cr.status st, COALESCE(m.status,'нет письма') ms, "
    "       COALESCE(NULLIF(m.last_error,''),'') le, m.sent_at "
    "  FROM confirm_reviews cr LEFT JOIN messages m ON m.id=cr.message_id "
    " WHERE cr.reason LIKE '%подтверждено 24.08, снято мной ошибочно%'"
    ).fetchall()
print("=== КОГОРТА «ПОДТВЕРЖДЕНО 24.08, ВОЗВРАЩЕНО 25.08»: %d ===" % len(когорта))
for к, н in Counter("карта %s / письмо %s" % (р["st"], р["ms"])
                    for р in когорта).most_common():
    print("   %-40s %5d" % (к, н))
беды = Counter(р["le"][:56] for р in когорта
               if р["ms"] not in ("sent", "scheduled") and р["le"])
if беды:
    print("   почему сняты:")
    for к, н in беды.most_common(8):
        print("      %-56s %4d" % (к, н))
ушли = [р for р in когорта if р["ms"] == "sent"]
if ушли:
    print("   отправлены:")
    for к, н in Counter(str(р["sent_at"])[:10] for р in ушли).most_common():
        print("      %s  %4d" % (к, н))

print("\n=== ОЧЕРЕДЬ ОТПРАВКИ СЕЙЧАС ===")
for р in c.execute(
        "SELECT COALESCE(cr.status,'нет карточки') st, COUNT(*) n "
        "  FROM messages m LEFT JOIN confirm_reviews cr ON cr.message_id=m.id "
        " WHERE m.status IN ('scheduled','sending') GROUP BY st ORDER BY n DESC"):
    print("   письмо scheduled, карточка %-14s %5d" % (р["st"], р["n"]))
print("\n=== ОТПРАВЛЕНО ПО ДНЯМ (последние 6) ===")
for р in c.execute("SELECT substr(sent_at,1,10) д, COUNT(*) n FROM messages "
                   " WHERE status='sent' AND sent_at IS NOT NULL "
                   " GROUP BY д ORDER BY д DESC LIMIT 6"):
    print("   %s  %5d" % (р["д"], р["n"]))
