# -*- coding: utf-8 -*-
"""N случайных pending-карточек кампании 22 с компанией, продукцией, адресом и ящиком — для глазной проверки. Только чтение.
    gaz_10_sluchaynyh.py [N=10] [seed]"""
import json, random, sqlite3, sys
c = sqlite3.connect("file:C:\\sender\\sender.db?mode=ro", uri=True, timeout=60)
ряды = c.execute("SELECT id, email, subject, COALESCE(edited_body, body), panel_json FROM confirm_reviews WHERE campaign_id=22 AND status='pending'").fetchall()
random.seed(int(sys.argv[2]) if len(sys.argv) > 2 else None)
for кид, em, тема, тело, pj in random.sample(ряды, int(sys.argv[1]) if len(sys.argv) > 1 else 10):
    д = json.loads(pj or "{}"); к = д.get("company") or {}
    print("=== #%d | %s | %s | ящик %s\n[%s | %s | оборуд: %s]\nТема: %s\n%s\n" % (кид, (к.get("name") or "")[:50], em, д.get("mailbox_id"),
          (д.get("gaz") or {}).get("otrasl", "")[:40], (к.get("activity") or "")[:180], (к.get("why_equipment") or "")[:120], тема, тело))
