# -*- coding: utf-8 -*-
"""Жив ли проход автоотправки: последние claimed_at/updated_at писем в очереди. Только чтение."""
import sqlite3
c = sqlite3.connect(r"C:\sender\sender.db", timeout=60)
print("сейчас UTC:", c.execute("SELECT strftime('%Y-%m-%dT%H:%M:%S','now')").fetchone()[0])
print("последний claimed_at:", c.execute("SELECT MAX(claimed_at) FROM messages").fetchone()[0])
print("последний updated_at scheduled:", c.execute("SELECT MAX(updated_at) FROM messages WHERE status='scheduled'").fetchone()[0])
print("в sending сейчас:", c.execute("SELECT id, campaign_id, mailbox_id, claimed_at FROM messages WHERE status='sending' ORDER BY claimed_at DESC LIMIT 5").fetchall())
