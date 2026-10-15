# -*- coding: utf-8 -*-
"""Где письма КЦ (кампания 15) после кнопки «В автоотправку»: статусы, время, ящик, ошибки."""
import sqlite3
c = sqlite3.connect(r"C:\sender\sender.db", timeout=30)
print(c.execute("SELECT status, count(*) FROM messages WHERE campaign_id=15 GROUP BY 1").fetchall())
print(c.execute("SELECT substr(scheduled_at,1,16), mailbox_id, substr(last_error,1,120) FROM messages WHERE campaign_id=15 "
                "AND status IN ('scheduled','sending','approved','failed') ORDER BY scheduled_at LIMIT 12").fetchall())
print("ошибки:", c.execute("SELECT substr(last_error,1,80), count(*) FROM messages WHERE campaign_id=15 AND last_error IS NOT NULL GROUP BY 1").fetchall())
print("карточки:", c.execute("SELECT status, count(*) FROM confirm_reviews WHERE campaign_id=15 GROUP BY 1").fetchall())
print("=== КЦ В АВТО ===")
