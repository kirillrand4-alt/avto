# -*- coding: utf-8 -*-
"""Только чтение: какие вердикты пробы снимают письмо с очереди. Итог в конце."""
import datetime as dt
import inspect
import re
import sqlite3
import sys

sys.path.insert(0, r"C:\sender")
import sender.addr_probe as AP  # noqa: E402

исх = inspect.getsource(AP)
н = исх.find("СНЯТЬ_С_ОЧЕРЕДИ")
print("=== ОПРЕДЕЛЕНИЕ СНЯТЬ_С_ОЧЕРЕДИ ===")
print(исх[max(0, н - 700):н + 500])

c = sqlite3.connect("file:C:/sender/sender.db?mode=ro", uri=True)
c.row_factory = sqlite3.Row
сейчас = dt.datetime.now()
у = сейчас.replace(hour=0, minute=0, second=0).isoformat()

print("\n=== КОГО СНЯЛИ ИЗ НАШЕЙ ПАРТИИ ===")
for р in c.execute("SELECT m.id, r.email, r.company_name, m.last_error"
                   " FROM messages m JOIN recipients r ON r.id=m.recipient_id"
                   " WHERE m.campaign_id=12 AND m.status='skipped'"):
    print("  %-34s %-24s %s" % (р["email"][:34], str(р["company_name"])[:24],
                                str(р["last_error"])[:56]))

print("\n=== ПРОГРЕСС ===")
print("  время %s" % сейчас.strftime("%H:%M:%S"))
print("  отправлено сегодня: %d"
      % c.execute("SELECT COUNT(*) FROM messages WHERE status='sent' AND sent_at>=?",
                  (у,)).fetchone()[0])
for р in c.execute("SELECT campaign_id, status, COUNT(*) k FROM messages"
                   " WHERE campaign_id IN (11,12) GROUP BY campaign_id, status"
                   " ORDER BY campaign_id, status"):
    print("  кампания %-3s %-14s %d" % (р["campaign_id"], р["status"], р["k"]))
