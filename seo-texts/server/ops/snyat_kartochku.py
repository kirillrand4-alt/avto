# -*- coding: utf-8 -*-
"""Снять pending-карточку (и её сообщение) по решению владельца: snyat_kartochku.py ID "причина" """
import sqlite3, sys
from datetime import datetime, timezone
c = sqlite3.connect(r"C:\sender\sender.db", timeout=90)
к, причина = int(sys.argv[1]), sys.argv[2]
т = datetime.now(timezone.utc).isoformat()
r = c.execute("SELECT status, email, message_id FROM confirm_reviews WHERE id=?", (к,)).fetchone()
print("было:", r)
with c:
    c.execute("UPDATE confirm_reviews SET status='skipped', reason=?, decided_at=?, updated_at=? WHERE id=? AND status='pending'", (причина, т, т, к))
    if r and r[2]:
        c.execute("UPDATE messages SET status='skipped', last_error=?, updated_at=? WHERE id=? AND status IN ('pending_review','scheduled')", (причина, т, r[2]))
print("стало:", c.execute("SELECT status, reason FROM confirm_reviews WHERE id=?", (к,)).fetchone())
