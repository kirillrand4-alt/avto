# -*- coding: utf-8 -*-
"""События suppress за сегодня: кого и почему внесли в стоп-лист."""
import json
import sqlite3
c = sqlite3.connect(r"C:\sender\sender.db", timeout=30)
c.row_factory = sqlite3.Row
for е in c.execute("SELECT e.event_ts, e.detail_json, r.email, r.company_name FROM events e LEFT JOIN recipients r "
                   "ON r.id=e.recipient_id WHERE e.event_type='suppress' AND e.created_at >= date('now')"):
    print("   %s | %s <%s> | %s" % (str(е["event_ts"])[:16], str(е["company_name"])[:30], е["email"],
                                   str(е["detail_json"])[:220]))
print("--- стоп-лист: добавлено сегодня по причинам ---")
for р in c.execute("SELECT reason, scope, count(*) FROM suppression WHERE created_at >= date('now') GROUP BY 1,2"):
    print("   %s | %s | %d" % (р[0], р[1], р[2]))
print("=== СТОП-ЛИСТ СЕГОДНЯ ===")
