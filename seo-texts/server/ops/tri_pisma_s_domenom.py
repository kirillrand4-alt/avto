# -*- coding: utf-8 -*-
"""Те три письма с основным доменом — холодные рассылки или ручные ответы?"""
import sqlite3
БАЗА = r"C:\sender\sender.db"
c = sqlite3.connect("file:%s?mode=ro" % БАЗА, uri=True, timeout=60)
c.row_factory = sqlite3.Row
for r in c.execute(
        "SELECT id, email, kind, status, decided_by, campaign_id, "
        "       COALESCE(decided_at, updated_at) ts, "
        "       COALESCE(edited_subject, subject) tema "
        "  FROM confirm_reviews "
        " WHERE LOWER(COALESCE(edited_body, body,'')) LIKE '%prokompressor%' "
        " ORDER BY ts"):
    print("review=%s %s | вид=%s статус=%s решил=%s кампания=%s"
          % (r["id"], str(r["ts"])[:19], r["kind"], r["status"],
             r["decided_by"], r["campaign_id"]))
    print("    кому: %-34s тема: %s" % (r["email"], str(r["tema"])[:60]))
print()
for r in c.execute(
        "SELECT m.id, m.sent_at, m.campaign_id, m.status, r.email "
        "  FROM messages m LEFT JOIN recipients r ON r.id=m.recipient_id "
        " WHERE LOWER(COALESCE(m.body_rendered,'')) LIKE '%prokompressor%'"):
    print("msg=%s %s кампания=%s %s -> %s"
          % (r["id"], str(r["sent_at"])[:19], r["campaign_id"], r["status"],
             r["email"]))
c.close()
