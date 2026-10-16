# -*- coding: utf-8 -*-
"""Запланированные письма с прошедшим временем: почему не ушли. Только чтение."""
import sqlite3
from datetime import datetime, timedelta
c = sqlite3.connect(r"C:\sender\sender.db", timeout=60)
кам = {r[0]: r[1] for r in c.execute("SELECT id, name FROM campaigns")}
пауза = {r[0]: r[1] for r in c.execute("SELECT mailbox_id, pause_reason FROM mailbox_state WHERE paused=1")}
сейчас = datetime.utcnow()
for mid, cid, st, sa, mb, att, err, tz, em in c.execute(
        "SELECT m.id, m.campaign_id, m.status, m.scheduled_at, m.mailbox_id, m.attempt_count, m.last_error, r.tz, r.email "
        "FROM messages m JOIN recipients r ON r.id=m.recipient_id WHERE m.status IN ('scheduled','approved','sending')"):
    try: t = datetime.fromisoformat(str(sa).replace(" ", "T")[:19])
    except Exception: t = None
    if t and t > сейчас - timedelta(minutes=30): continue
    print(mid, кам.get(cid), st, sa, "| ящик", mb, ("ПАУЗА: " + str(пауза.get(mb))) if mb in пауза else "", "| попыток", att, "| tz", tz, "|", em, "|", str(err or "")[:90])
