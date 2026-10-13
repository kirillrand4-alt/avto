# -*- coding: utf-8 -*-
"""Отбои (баунсы) за последние N часов: кому, с какого ящика, текст причины, вердикт пробы."""
import json
import sqlite3
import sys
ч = int(sys.argv[1]) if len(sys.argv) > 1 else 12
c = sqlite3.connect(r"C:\sender\sender.db", timeout=30)
c.row_factory = sqlite3.Row
for е in c.execute("SELECT e.*, r.email, r.company_name, r.mx_provider FROM events e "
                   "LEFT JOIN recipients r ON r.id=e.recipient_id "
                   "WHERE e.event_type LIKE '%bounce%' AND e.created_at >= datetime('now', ?) "
                   "ORDER BY e.id", ("-%d hours" % ч,)):
    try:
        d = json.loads(е["detail_json"] or "{}")
    except Exception:  # noqa: BLE001
        d = {}
    п = c.execute("SELECT verdict, ts || ' ' || coalesce(source,'') AS ts FROM addr_probe WHERE email=?", (str(е["email"] or "").lower(),)).fetchone()
    м = c.execute("SELECT sent_at, mailbox_id FROM messages WHERE id=?", (е["message_id"],)).fetchone()
    print("## %s %s | %s <%s> mx=%s | ящик %s | ушло %s | проба: %s" % (
        е["event_ts"][:16], е["event_type"], str(е["company_name"])[:30], е["email"], е["mx_provider"],
        е["mailbox_id"] or (м and м["mailbox_id"]), м and str(м["sent_at"])[:16],
        (п["verdict"] + " " + str(п["ts"])[:40]) if п else "нет"))
    for к in ("code", "status", "diagnostic", "reason", "smtp_code", "text", "snippet", "kind"):
        if d.get(к):
            print("   %s: %s" % (к, str(d[к])[:300].replace("\n", " ")))
print("=== БАУНСЫ ===")
