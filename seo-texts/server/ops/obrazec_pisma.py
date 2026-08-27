# -*- coding: utf-8 -*-
import sqlite3
c = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\sender.db", uri=True, timeout=60)
c.row_factory = sqlite3.Row
for r in c.execute("SELECT m.subject, m.body_rendered, r.email, r.contact_name, "
                   "       r.company_name, m.campaign_id, m.mailbox_id "
                   "  FROM messages m JOIN recipients r ON r.id=m.recipient_id "
                   " WHERE m.status='sent' AND m.body_rendered IS NOT NULL "
                   "   AND m.subject NOT LIKE 'Re:%' "
                   "   AND m.in_reply_to IS NULL "
                   " ORDER BY m.id DESC LIMIT 2"):
    print("=" * 70)
    print("кому: %s | контакт: %r | кампания %s | ящик %s"
          % (r["email"], r["contact_name"], r["campaign_id"], r["mailbox_id"]))
    print("тема: %s" % r["subject"])
    print("-" * 70)
    print(r["body_rendered"])
c.close()
