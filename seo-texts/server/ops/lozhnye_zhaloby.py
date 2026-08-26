# -*- coding: utf-8 -*-
"""Кого стоп-лист съел по слову «спам» в тексте письма."""
import json
import sqlite3

c = sqlite3.connect(r"C:\sender\sender.db", timeout=90)
c.execute("PRAGMA busy_timeout=60000")
c.row_factory = sqlite3.Row
ряды = c.execute("SELECT value, reason, source, created_at FROM suppression "
                 " WHERE reason='complaint' OR source LIKE '%complaint%' "
                 " ORDER BY created_at DESC").fetchall()
print("адресов в стоп-листе по жалобе: %d" % len(ряды))
for r in ряды[:15]:
    rec = c.execute("SELECT company_name FROM recipients WHERE email=?",
                    (r["value"],)).fetchone()
    print("   %-34s %-18s %s  %s" % (r["value"][:34], r["source"],
                                     str(r["created_at"])[:16],
                                     str(rec["company_name"])[:34] if rec else ""))

print("")
print("=== отбивка akkermann: что ответил их сервер ===")
for r in c.execute("SELECT e.detail_json, r.email FROM events e "
                   "  LEFT JOIN recipients r ON r.id=e.recipient_id "
                   " WHERE e.detail_json LIKE '%akkermann%' "
                   " ORDER BY e.id DESC LIMIT 2"):
    d = json.loads(r["detail_json"] or "{}")
    т = " ".join(str(d.get("snippet") or "").split())
    print("   %s" % str(r["email"] or "")[:40])
    print("   %s" % т[:700])
c.close()
