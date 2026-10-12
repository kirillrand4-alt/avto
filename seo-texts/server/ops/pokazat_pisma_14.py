# -*- coding: utf-8 -*-
"""Показать последние готовые письма кампании 14 из очереди подтверждения."""
import sqlite3
import sys
n = int(sys.argv[1]) if len(sys.argv) > 1 else 5
сдвиг = int(sys.argv[2]) if len(sys.argv) > 2 else 0
c = sqlite3.connect(r"C:\sender\sender.db", timeout=30)
c.row_factory = sqlite3.Row
for р in c.execute(
        "SELECT cr.id, cr.email, cr.subject, cr.body, r.company_name, r.segment "
        "FROM confirm_reviews cr LEFT JOIN recipients r ON r.id=cr.recipient_id "
        "WHERE cr.campaign_id=14 AND cr.status='pending' "
        "ORDER BY cr.id DESC LIMIT ? OFFSET ?", (n, сдвиг)):
    print("#%s | %s | %s | %s" % (р["id"], (р["company_name"] or "")[:40],
                                 р["segment"] or "", р["email"]))
    print("ТЕМА: %s" % р["subject"])
    тело = (р["body"] or "").split("С уважением")[0].strip()
    print(тело)
    print("-" * 60)
print("=== ПИСЬМА 14 ===")
