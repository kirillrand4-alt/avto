# -*- coding: utf-8 -*-
"""N случайных писем кампании (тема + текст + компания), счёт статусов. Только чтение.  kampaniya_obrazcy.py <id> [n=3]"""
import json, random, sqlite3, sys
к = int(sys.argv[1]); n = int(sys.argv[2]) if len(sys.argv) > 2 else 3
c = sqlite3.connect("file:C:\\sender\\sender.db?mode=ro", uri=True)
print("карточки:", c.execute("SELECT status, COUNT(*) FROM confirm_reviews WHERE campaign_id=? GROUP BY 1", (к,)).fetchall())
р = c.execute("SELECT id, subject, body, panel_json FROM confirm_reviews WHERE campaign_id=? AND status='pending'", (к,)).fetchall()
random.seed(7)
for кид, т, б, pj in random.sample(р, min(n, len(р))):
    д = json.loads(pj or "{}")
    print("\n=== #%s | %s\nТема: %s\n%s" % (кид, (д.get("company") or {}).get("name", ""), т, б))
