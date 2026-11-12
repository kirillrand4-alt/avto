# -*- coding: utf-8 -*-
"""Статусы кампании 22: карточки подтверждения и сообщения (только чтение)."""
import sqlite3
c = sqlite3.connect("file:C:\\sender\\sender.db?mode=ro", uri=True, timeout=60)
print("карточки:", c.execute("SELECT status, COUNT(*) FROM confirm_reviews WHERE campaign_id=22 GROUP BY status").fetchall())
print("сообщения:", c.execute("SELECT status, COUNT(*) FROM messages WHERE campaign_id=22 GROUP BY status").fetchall())
print("отправлено сегодня:", c.execute("SELECT COUNT(*) FROM messages WHERE campaign_id=22 AND status='sent'").fetchone()[0])
