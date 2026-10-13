# -*- coding: utf-8 -*-
"""Найти входящее и всё про компанию: события, лиды, получатели, наши письма.

    nayti_vhodyashchee.py <адрес> "<кусок названия компании>"
"""
import sqlite3
import sys
адрес, назв = sys.argv[1].lower(), sys.argv[2]
c = sqlite3.connect(r"C:\sender\sender.db", timeout=30)
c.row_factory = sqlite3.Row
def табл(t):
    return [r[1] for r in c.execute("PRAGMA table_info(%s)" % t)]
print("events кол:", табл("events")[:14])
for р in c.execute("SELECT id, event_ts, event_type, message_id, recipient_id, campaign_id, mailbox_id, substr(detail_json,1,300) d FROM events "
                   "WHERE lower(detail_json) LIKE ? ORDER BY id DESC LIMIT 6", ("%" + адрес + "%",)):
    print("событие", dict(р))
for р in c.execute("SELECT id, email, company_name, inn, status, reply_kind, created_at FROM leads "
                   "WHERE lower(email)=? OR company_name LIKE ? ORDER BY id DESC LIMIT 5", (адрес, "%" + назв + "%")):
    print("лид", dict(р))
for р in c.execute("SELECT id, email, company_name, inn, segment FROM recipients "
                   "WHERE lower(email)=? OR company_name LIKE ? OR company_name LIKE ? LIMIT 8",
                   (адрес, "%" + назв + "%", "%" + назв.upper() + "%")):
    print("получатель", dict(р))
    for м in c.execute("SELECT id, campaign_id, status, mailbox_id, subject, sent_at FROM messages "
                       "WHERE recipient_id=? ORDER BY id DESC LIMIT 3", (р["id"],)):
        print("   письмо", dict(м))
print("=== НАЙТИ ВХОДЯЩЕЕ ===")
