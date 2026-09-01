# -*- coding: utf-8 -*-
"""Только чтение: _last_sent_mailbox — откуда берётся указатель ротации."""
import io
import re
import sqlite3

стр = io.open(r"C:\sender\sender\sender.py", encoding="utf-8",
              errors="replace").read().splitlines()
н = [i for i, x in enumerate(стр) if re.search(r"def _last_sent_mailbox", x)]
print("=== найдено определений: %s ===" % н)

s = sqlite3.connect("file:C:/sender/sender.db?mode=ro", uri=True)
s.row_factory = sqlite3.Row
print("\n=== mailbox_state.last_sent_at у meyer-ящиков ===")
for р in s.execute("SELECT mailbox_id, last_sent_at, sent_total FROM mailbox_state"
                   " ORDER BY COALESCE(last_sent_at,'') DESC"):
    m = str(р["mailbox_id"])
    if any(x in m for x in ("sort", "zerno", "rentgen", "inspection", "food")):
        print("  %-40s %-26s всего %s"
              % (m[:40], str(р["last_sent_at"])[:24], р["sent_total"]))

print("\n=== ИТОГ: текст _last_sent_mailbox ===")
if н:
    i = н[0]
    for j in range(i, min(i + 26, len(стр))):
        print("  %4d  %s" % (j + 1, стр[j][:110]))
