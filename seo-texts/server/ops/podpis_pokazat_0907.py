# -*- coding: utf-8 -*-
"""Только чтение: что именно дописывается в подпись письма."""
import sqlite3

c = sqlite3.connect("file:C:/sender/sender.db?mode=ro", uri=True)
c.row_factory = sqlite3.Row
for р in c.execute("SELECT m.id, m.body_rendered b FROM messages m"
                   " WHERE m.status='sent' AND m.body_rendered<>''"
                   " ORDER BY m.id DESC LIMIT 1"):
    т = р["b"] or ""
    i = т.find("С уважением")
    print("=== ХВОСТ ПОСЛЕДНЕГО ОТПРАВЛЕННОГО ПИСЬМА (id=%s) ===" % р["id"])
    print(т[i:i + 900] if i >= 0 else т[-900:])
