# -*- coding: utf-8 -*-
"""Что ушло за день (UTC-дата, по умолчанию сегодня): холодные письма по кампаниям и напоминания."""
import sqlite3, sys
from datetime import datetime, timezone
д = sys.argv[1] if len(sys.argv) > 1 else datetime.now(timezone.utc).strftime("%Y-%m-%d")
c = sqlite3.connect(r"C:\sender\sender.db", timeout=60)
print("== письма (messages) за", д)
for r in c.execute("SELECT c.name, CASE WHEN m.subject LIKE 'Re:%' THEN 'Re:' ELSE 'новое' END, COUNT(*) FROM messages m LEFT JOIN campaigns c ON c.id=m.campaign_id "
                   "WHERE m.status='sent' AND substr(m.sent_at,1,10)=? GROUP BY 1,2 ORDER BY 3 DESC", (д,)):
    print("  ", r)
print("== карточки-ответы (kind=reply) за", д)
for r in c.execute("SELECT CASE WHEN panel_json LIKE '%napominanie%' THEN 'напоминание' ELSE 'ручной ответ' END, COUNT(*) FROM confirm_reviews "
                   "WHERE kind='reply' AND status='sent' AND substr(decided_at,1,10)=? GROUP BY 1", (д,)):
    print("  ", r)
