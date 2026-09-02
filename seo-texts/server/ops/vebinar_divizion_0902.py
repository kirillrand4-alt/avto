# -*- coding: utf-8 -*-
"""Только чтение: как выбирается ящик для письма кампании 12 и не уйдёт ли
оно с компрессорного ящика."""
import inspect
import io
import re
import sqlite3
import sys

sys.path.insert(0, r"C:\sender")
import sender.sender as SS  # noqa: E402

print("=== откуда берётся дивизион письма ===")
т = io.open(r"C:\sender\sender\sender.py", encoding="utf-8", errors="replace").read()
лн = т.splitlines()
for м in re.finditer(r"def pick_mailbox|division", т):
    н = т[:м.start()].count("\n")
    с = лн[н].strip()
    if "division" in с and any(k in с for k in ("=", "def ", "if ", "get(")):
        print("  sender.py:%d  %s" % (н + 1, с[:104]))

print("\n=== pick_mailbox: первые 40 строк ===")
ф = getattr(SS.Sender, "pick_mailbox", None) or getattr(SS, "pick_mailbox", None)
if ф:
    for л in inspect.getsource(ф).splitlines()[:40]:
        print("  " + л[:104])

c = sqlite3.connect("file:C:/sender/sender.db?mode=ro", uri=True)
c.row_factory = sqlite3.Row
print("\n=== КАМПАНИЯ 12: ЧТО УЖЕ УШЛО ===")
for x in c.execute("SELECT status, mailbox_id, COUNT(*) n FROM messages"
                   " WHERE campaign_id=12 GROUP BY status, mailbox_id"):
    print("  %-14s %-34s %4d" % (x["status"], x["mailbox_id"] or "(ротация)", x["n"]))
пос = c.execute("SELECT id, mailbox_id, sent_at, subject FROM messages"
                " WHERE campaign_id=12 AND status='sent' ORDER BY sent_at DESC"
                " LIMIT 5").fetchall()
for р in пос:
    print("  ушло: %s | %s | %s" % (р["sent_at"], р["mailbox_id"], str(р["subject"])[:40]))
print("  всего отправлено по кампании 12: %d" % len(пос))
