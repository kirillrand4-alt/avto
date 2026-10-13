# -*- coding: utf-8 -*-
"""Входящие «вне переписки» за 3 дня: события и лиды, к кому привязаны."""
import json
import sqlite3
c = sqlite3.connect(r"C:\sender\sender.db", timeout=30)
c.row_factory = sqlite3.Row
print("--- лиды с видом «вне переписки» / без получателя (3 дня) ---")
for л in c.execute("SELECT id, email, company_name, inn, status, reply_kind, recipient_id, created_at FROM leads "
                   "WHERE created_at >= datetime('now','-3 days') AND (reply_kind='вне переписки' OR recipient_id IS NULL)"):
    print("   лид #%s %s <%s> ИНН %s | %s | %s | rid %s | %s" % (л["id"], str(л["company_name"])[:30], л["email"], л["inn"],
          л["status"], л["reply_kind"], л["recipient_id"], str(л["created_at"])[:16]))
print("--- входящие события без получателя (3 дня) ---")
for е in c.execute("SELECT id, event_type, event_ts, mailbox_id, detail_json FROM events WHERE created_at >= datetime('now','-3 days') "
                   "AND recipient_id IS NULL AND event_type IN ('reply','reply_auto','inbound','vne_perepiski','reply_unmatched','unmatched')"):
    try:
        d = json.loads(е["detail_json"] or "{}")
    except Exception:  # noqa: BLE001
        d = {}
    print("   событие #%s %s %s ящик %s | от %s | %s | %s" % (е["id"], е["event_type"], str(е["event_ts"])[:16], е["mailbox_id"],
          d.get("from") or d.get("sender") or d.get("email"), str(d.get("subject"))[:50], str(d.get("snippet"))[:120].replace("\n", " ")))
print("--- типы событий за 3 дня ---")
for т, n in c.execute("SELECT event_type, count(*) FROM events WHERE created_at >= datetime('now','-3 days') GROUP BY 1"):
    print("   %s %d" % (т, n))
print("=== ВНЕ ПЕРЕПИСКИ ===")
for е in c.execute("SELECT * FROM events WHERE event_type='other' AND created_at >= datetime('now','-3 days')"):
    е = dict(е)
    d = json.loads(е.get("detail_json") or "{}")
    print("СОБЫТИЕ other #%s ts %s ящик %s rid %s msg %s" % (е["id"], е["event_ts"], е["mailbox_id"], е["recipient_id"], е["message_id"]))
    for к, v in d.items():
        print("   %s: %s" % (к, str(v)[:400].replace("\n", " ")))
