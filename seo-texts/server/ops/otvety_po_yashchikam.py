# -*- coding: utf-8 -*-
"""Отправлено и получено — по каждому ящику. Ищем перекос.

Если у ящика много отправок и почти нет ответов, а у соседнего наоборот —
значит ответы уходят не туда, где их читают.
"""
import sqlite3
import sys

sys.path.insert(0, r"C:\sender")
from sender.config import Config              # noqa: E402

cfg = Config.load(r"C:\sender\sender.yaml")
в_настройках = {mb.mailbox_id for mb in cfg.mailboxes()}

c = sqlite3.connect(r"C:\sender\sender.db", timeout=90)
c.execute("PRAGMA busy_timeout=60000")
c.row_factory = sqlite3.Row

отпр = {r["mailbox_id"]: r["n"] for r in c.execute(
    "SELECT mailbox_id, COUNT(*) n FROM messages WHERE sent_at IS NOT NULL "
    " GROUP BY mailbox_id")}
вход = {}
for r in c.execute("SELECT mailbox_id, event_type, COUNT(*) n FROM events "
                   " WHERE event_type IN ('reply','reply_auto','bounce','other') "
                   " GROUP BY mailbox_id, event_type"):
    вход.setdefault(r["mailbox_id"] or "", {})[r["event_type"]] = r["n"]

все = sorted(set(отпр) | set(вход) | в_настройках, key=lambda x: -отпр.get(x, 0))
print("%-42s %7s %7s %7s %7s %7s  %s"
      % ("ящик", "ушло", "ответ", "авто", "отбив", "%", "в настройках"))
итого = [0, 0, 0]
for я in все:
    о = отпр.get(я, 0)
    в = вход.get(я, {})
    отв, авт, отб = в.get("reply", 0), в.get("reply_auto", 0), в.get("bounce", 0)
    итого[0] += о
    итого[1] += отв + авт
    итого[2] += отб
    доля = (100.0 * (отв + авт) / о) if о else 0
    print("%-42s %7d %7d %7d %7d %6.1f%%  %s"
          % (str(я)[:42], о, отв, авт, отб, доля,
             "да" if я in в_настройках else "НЕТ"))
print("%-42s %7d %7d %7s %7d %6.1f%%"
      % ("ИТОГО", итого[0], итого[1], "", итого[2],
         100.0 * итого[1] / итого[0] if итого[0] else 0))

print("")
print("=== отправки без ящика в настройках ===")
чужие = [я for я in отпр if я not in в_настройках]
for я in чужие:
    print("   %-42s ушло %d" % (str(я)[:42], отпр[я]))
if not чужие:
    print("   таких нет")
c.close()
