# -*- coding: utf-8 -*-
"""Входящий ответ по адресу: заголовки From/To/Cc, тело; наше исходное письмо
(тема, текст, ящик). Только чтение. otvet_kopiya.py <email отправителя>"""
import json
import sqlite3
import sys

c = sqlite3.connect(r"C:\sender\sender.db")
em = sys.argv[1].lower()
for eid, ts, dj, rid in c.execute("SELECT e.id, e.event_ts, e.detail_json, e.recipient_id FROM events e JOIN recipients r ON r.id=e.recipient_id "
                                  "WHERE e.event_type='reply' AND (lower(r.email)=? OR lower(e.detail_json) LIKE ?) ORDER BY e.id",
                                  (em, "%" + em + "%")):
    d = json.loads(dj or "{}")
    h = d.get("headers") or {}
    print("=== ответ %s %s" % (eid, ts))
    for k in ("From", "To", "Cc", "CC", "Subject"):
        if h.get(k):
            print("  %s: %s" % (k, h[k]))
    for k, v in d.items():
        if k != "headers" and isinstance(v, str) and len(v) > 50:
            print("  [%s] %s" % (k, v[:1500]))
    r = c.execute("SELECT r.email, r.inn, r.company_name, m.mailbox_id, cr.subject, cr.body FROM recipients r "
                  "LEFT JOIN messages m ON m.recipient_id=r.id AND m.status='sent' LEFT JOIN confirm_reviews cr ON cr.message_id=m.id "
                  "WHERE r.id=? ORDER BY m.id DESC LIMIT 1", (rid,)).fetchone()
    print("\nнаше письмо:", r[:5] if r else None)
    if r and r[5]:
        print(str(r[5]).split("\n\nС уважением,")[0][:1500])
