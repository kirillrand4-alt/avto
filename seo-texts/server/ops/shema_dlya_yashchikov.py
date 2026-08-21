# -*- coding: utf-8 -*-
"""Схема: какими колонками хранится ящик-отправитель и направление ящика."""
import sqlite3

c = sqlite3.connect(r"C:\sender\sender.db")
c.row_factory = sqlite3.Row
табл = [р[0] for р in c.execute(
    "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
print("таблицы:", ", ".join(табл))
for т in ("messages", "confirm_reviews", "mailboxes", "mailbox_state",
          "recipients", "campaigns"):
    if т not in табл:
        continue
    к = [р[1] for р in c.execute(f"PRAGMA table_info({т})")]
    print(f"\n{т}: {', '.join(к)}")
for т in табл:
    if "mail" in т or "box" in т or "yash" in т:
        к = [р[1] for р in c.execute(f"PRAGMA table_info({т})")]
        n = c.execute(f"SELECT COUNT(*) FROM {т}").fetchone()[0]
        print(f"\n[ящики?] {т} ({n}): {', '.join(к)}")
        for р in c.execute(f"SELECT * FROM {т} LIMIT 3"):
            print("   ", dict(р))
