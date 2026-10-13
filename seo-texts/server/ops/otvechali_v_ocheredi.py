# -*- coding: utf-8 -*-
"""Письма в очереди компаниям, которые нам отвечали (живой лид) — снять (--snyat)."""
import sqlite3
import sys
from collections import Counter
from datetime import datetime, timezone
c = sqlite3.connect(r"C:\sender\sender.db", timeout=30)
c.row_factory = sqlite3.Row
строки = [dict(р) for р in c.execute(
    "SELECT m.id, m.status, m.campaign_id, r.inn, r.company_name, "
    "(SELECT status FROM leads l WHERE l.inn=r.inn AND l.status NOT IN ('avtootvet','v_otpuske','deleted') "
    " AND coalesce(l.reply_kind,'') NOT IN ('auto_reply') LIMIT 1) AS лид "
    "FROM messages m JOIN recipients r ON r.id=m.recipient_id "
    "WHERE m.status IN ('scheduled','pending_review') AND coalesce(r.inn,'')<>''")]
есть = [р for р in строки if р["лид"]]
print("в очереди писем компаниям, которые отвечали: %d; по статусу: %s; по лиду: %s" % (
    len(есть), dict(Counter(р["status"] for р in есть)), dict(Counter(р["лид"] for р in есть))))
for р in есть[:10]:
    print("   m%s %s камп %s | %s | лид %s" % (р["id"], р["status"], р["campaign_id"], str(р["company_name"])[:34], р["лид"]))
if "--snyat" in sys.argv and есть:
    т = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
    with c:
        n = c.executemany("UPDATE messages SET status='skipped', last_error=?, updated_at=? WHERE id=? "
                          "AND status IN ('scheduled','pending_review')",
                          [("снято 13.10: компания нам отвечала (лид %s)" % р["лид"], т, р["id"]) for р in есть]).rowcount
    print("снято: %d" % n)
print("=== ОТВЕЧАЛИ В ОЧЕРЕДИ ===")
