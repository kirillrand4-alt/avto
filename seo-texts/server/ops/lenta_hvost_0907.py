# -*- coding: utf-8 -*-
"""Только чтение: письма компании, методы стора, хвост прецедента (как применяет)."""
import io
import inspect
import sqlite3
import sys

c = sqlite3.connect("file:C:/sender/sender.db?mode=ro", uri=True)
c.row_factory = sqlite3.Row
print("=== ПИСЬМА ЭТОЙ КОМПАНИИ (recipient 33093) ===")
for m in c.execute("SELECT id, campaign_id, status, sent_at, mailbox_id,"
                   " subject FROM messages WHERE recipient_id=33093 ORDER BY id"):
    print("  msg=%s камп=%s %-9s %s ящик=%s | %s"
          % (m["id"], m["campaign_id"], m["status"], str(m["sent_at"])[:19],
             m["mailbox_id"], str(m["subject"])[:45]))

sys.path.insert(0, r"C:\sender")
from sender.store import Store                                   # noqa: E402
print("\n=== МЕТОДЫ Store про лиды/события ===")
for и, ф in inspect.getmembers(Store, inspect.isfunction):
    if "lead" in и.lower() or "event" in и.lower():
        try:
            print("  %s%s" % (и, str(inspect.signature(ф))[:140]))
        except (TypeError, ValueError):
            print("  %s" % и)

т = io.open(r"C:\sender\server\ops\vernut_otvety_iz_other.py",
            encoding="utf-8", errors="ignore").read()
i = т.find("if not КАТИТЬ")
print("\n" + "=" * 20 + " ХВОСТ vernut_otvety_iz_other.py " + "=" * 20)
print(т[i:i + 3000])
