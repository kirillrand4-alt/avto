# -*- coding: utf-8 -*-
"""Созревшие scheduled-письма: по кампаниям и статусу последнего ревью (claim берёт только approved/edited). Только чтение."""
import sqlite3
c = sqlite3.connect("file:C:\\sender\\sender.db?mode=ro", uri=True)
for r in c.execute("""SELECT m.campaign_id, (SELECT cr.status FROM confirm_reviews cr WHERE cr.message_id=m.id ORDER BY cr.id DESC LIMIT 1) s,
                      COUNT(*) FROM messages m WHERE m.status='scheduled' AND m.scheduled_at<=strftime('%Y-%m-%dT%H:%M:%S','now') GROUP BY 1,2 ORDER BY 3 DESC"""): print(r)
print("sent по кампаниям сегодня:", c.execute("SELECT campaign_id, COUNT(*) FROM messages WHERE status='sent' AND sent_at>='2026-11-13' GROUP BY 1").fetchall())
