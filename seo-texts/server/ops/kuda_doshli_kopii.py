# -*- coding: utf-8 -*-
"""Что стало с копиями: мои семь и те, о которых пишет соседняя сессия."""
import sqlite3
import sys

АДРЕСА = [a.lower() for a in sys.argv[1:] if "@" in a]
МОИ = (2601, 3050, 3051, 3312, 3313, 3472, 3473)
c = sqlite3.connect(r"C:\sender\sender.db")
c.row_factory = sqlite3.Row

print("== семь копий, которые я поправил ==")
for rid in МОИ:
    r = c.execute(
        "SELECT cr.id, cr.status, cr.email, cr.message_id, COALESCE(cr.reason,'') rs, "
        "       (SELECT status FROM messages WHERE id=cr.message_id) mst, "
        "       (SELECT substr(scheduled_at,1,16) FROM messages "
        "        WHERE id=cr.message_id) slot, "
        "       rc.company_name "
        "FROM confirm_reviews cr LEFT JOIN recipients rc "
        "ON rc.id=cr.recipient_id WHERE cr.id=?", (rid,)).fetchone()
    if not r:
        print(f"  #{rid} нет")
        continue
    ушло = c.execute("SELECT COUNT(*) FROM send_log WHERE message_id=?",
                     (r["message_id"],)).fetchone()[0]
    print(f"  #{rid} {str(r['company_name'])[:28]:<28} {r['email']:<32} "
          f"карточка={r['status']:<9} письмо={r['mst']} слот={r['slot']} "
          f"в send_log={ушло}")

if АДРЕСА:
    print("\n== адреса из отчёта соседней сессии ==")
    for а in АДРЕСА:
        было = False
        for r in c.execute(
                "SELECT cr.id, cr.status, COALESCE(cr.reason,'') rs, "
                "       cr.message_id, rc.company_name, "
                "       (SELECT status FROM messages WHERE id=cr.message_id) mst "
                "FROM confirm_reviews cr LEFT JOIN recipients rc "
                "ON rc.id=cr.recipient_id WHERE lower(cr.email)=?", (а,)):
            было = True
            ушло = c.execute("SELECT COUNT(*) FROM send_log WHERE message_id=?",
                             (r["message_id"],)).fetchone()[0]
            print(f"  {а:<30} #{r['id']} {str(r['company_name'])[:24]:<24} "
                  f"{r['status']:<9} письмо={r['mst']} ушло={ушло}")
            if r["rs"]:
                print(f"      причина: {str(r['rs'])[:110]}")
        if not было:
            print(f"  {а:<30} карточки нет вовсе")
