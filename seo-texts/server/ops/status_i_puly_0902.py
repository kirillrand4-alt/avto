# -*- coding: utf-8 -*-
"""Только чтение: текущий ход отправки и как заданы пулы в конфиге."""
import datetime as dt
import io
import re
import sqlite3
import sys

sys.path.insert(0, r"C:\sender")
from sender.config import Config  # noqa: E402

cfg = Config.load(r"C:\sender\sender.yaml")
print("=== provider_split В КОНФИГЕ ===")
т = io.open(r"C:\sender\sender.yaml", encoding="utf-8", errors="replace").read()
лн = т.splitlines()
н = next((i for i, л in enumerate(лн) if л.startswith("provider_split")), None)
if н is not None:
    for i in range(н, min(н + 40, len(лн))):
        if лн[i].strip() and not лн[i].startswith(" ") and i > н:
            break
        print("  %4d| %s" % (i + 1, лн[i][:100]))

print("\n=== ГДЕ ОПИСАН pool_mailru ===")
for i, л in enumerate(лн):
    if "pool_mailru" in л:
        print("  %4d| %s" % (i + 1, л[:100]))

c = sqlite3.connect("file:C:/sender/sender.db?mode=ro", uri=True)
c.row_factory = sqlite3.Row
сейчас = dt.datetime.now()
у = сейчас.replace(hour=0, minute=0, second=0).isoformat()
print("\n=== ХОД ОТПРАВКИ %s ===" % сейчас.strftime("%H:%M:%S"))
print("  отправлено сегодня: %d"
      % c.execute("SELECT COUNT(*) FROM messages WHERE status='sent' AND sent_at>=?",
                  (у,)).fetchone()[0])
for р in c.execute("SELECT campaign_id, status, COUNT(*) k FROM messages"
                   " WHERE campaign_id IN (11,12) GROUP BY campaign_id, status"
                   " ORDER BY campaign_id, status"):
    print("  кампания %-3s %-14s %d" % (р["campaign_id"], р["status"], р["k"]))
print("  по ящикам за сегодня:")
for р in c.execute("SELECT mailbox_id, COUNT(*) k FROM messages WHERE status='sent'"
                   " AND sent_at>=? GROUP BY mailbox_id ORDER BY k DESC", (у,)):
    print("    %-36s %d" % (р["mailbox_id"], р["k"]))
