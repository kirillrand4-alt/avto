# -*- coding: utf-8 -*-
"""Снять карточки с подтверждения по id (владелец 16.10: «6 писем снимай» —
компании в Bitrix/переписке и повтор раньше 30 дней). Карточка и её письмо ->
skipped с причиной.

    snyat_kartochki.py <id,id,...> "<причина>"
"""
import sqlite3
import sys
import time

ид = [int(x) for x in sys.argv[1].split(",")]
причина = sys.argv[2] if len(sys.argv) > 2 else "снято владельцем"
т = time.strftime("%Y-%m-%dT%H:%M:%S")
c = sqlite3.connect(r"C:\sender\sender.db", timeout=60)
n = 0
with c:
    for i in ид:
        row = c.execute("SELECT message_id FROM confirm_reviews WHERE id=? AND status='pending'", (i,)).fetchone()
        if not row:
            print("#%d не pending, пропуск" % i)
            continue
        c.execute("UPDATE confirm_reviews SET status='skipped', reason=?, decided_at=?, updated_at=? WHERE id=?",
                  (причина, т, т, i))
        if row[0]:
            c.execute("UPDATE messages SET status='skipped', last_error=?, updated_at=? "
                      "WHERE id=? AND status IN ('pending_review','approved','scheduled')", (причина, т, row[0]))
        n += 1
print("снято:", n)
