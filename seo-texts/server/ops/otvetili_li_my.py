# -*- coding: utf-8 -*-
"""Отвечали ли мы этим лидам после их ответа (reply_sent по получателю)."""
import sqlite3
import sys
ид = [int(x) for x in sys.argv[1].split(",")]
c = sqlite3.connect(r"C:\sender\sender.db", timeout=30)
c.row_factory = sqlite3.Row
for лид in ид:
    л = c.execute("SELECT id, company_name, recipient_id, created_at, status FROM leads WHERE id=?", (лид,)).fetchone()
    if not л:
        continue
    н = c.execute("SELECT count(*) FROM events WHERE recipient_id=? AND event_type='reply_sent' "
                  "AND event_ts >= ?", (л["recipient_id"], л["created_at"])).fetchone()[0]
    print("#%s %-32s %s | наших ответов после: %d" % (лид, str(л["company_name"])[:32], л["status"], н))
print("=== ОТВЕТИЛИ ЛИ МЫ ===")
