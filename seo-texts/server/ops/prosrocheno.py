# -*- coding: utf-8 -*-
"""Что просрочено: письма со слотом в прошлом."""
import sqlite3
from collections import Counter
from datetime import datetime, timezone
c = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\sender.db", uri=True, timeout=60)
c.row_factory = sqlite3.Row
сейчас = datetime.now(timezone.utc).isoformat()
print("сейчас (UTC): %s" % сейчас[:19])
строки = c.execute(
    "SELECT m.id, m.status, m.scheduled_at, m.mailbox_id, m.campaign_id, "
    "       rc.email, rc.tz, rc.company_name, cr.id crid, cr.status crst "
    "  FROM messages m JOIN recipients rc ON rc.id=m.recipient_id "
    "  LEFT JOIN confirm_reviews cr ON cr.message_id=m.id "
    " WHERE m.status IN ('scheduled','sending') AND m.scheduled_at < ? "
    " ORDER BY m.scheduled_at", (сейчас,)).fetchall()
print("писем со слотом в прошлом: %d" % len(строки))
print("")
print("=== по дням слота ===")
for к, n in Counter(str(r["scheduled_at"])[:10] for r in строки).most_common():
    print("   %s  %3d" % (к, n))
print("")
print("=== по ящикам ===")
for к, n in Counter(str(r["mailbox_id"] or "—") for r in строки).most_common(8):
    print("   %-36s %3d" % (к[:36], n))
print("")
print("=== список ===")
for r in строки[:26]:
    print("   msg %-6s %-8s слот %s  %-26s %-24s tz=%s"
          % (r["id"], r["status"], str(r["scheduled_at"])[:16],
             str(r["email"])[:26], str(r["company_name"] or "")[:24],
             str(r["tz"] or "—")[:16]))
# лиды с просроченным SLA — на случай, если речь про них
n = c.execute("SELECT COUNT(*) FROM leads WHERE sla_due_at < ? "
              "  AND status IN ('new','assigned','taken')", (сейчас,)).fetchone()[0]
print("")
print("лидов с просроченным SLA: %d" % n)
c.close()
