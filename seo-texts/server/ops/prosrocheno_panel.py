# -*- coding: utf-8 -*-
"""Ровно «просрочено» панели (store.skolko_zhdyot_otpravki): scheduled/sending,
sent_at пуст, дата scheduled_at раньше сегодняшней (UTC). С карточками. Только чтение."""
import sqlite3
c = sqlite3.connect(r"C:\sender\sender.db", timeout=60)
кам = {r[0]: r[1] for r in c.execute("SELECT id, name FROM campaigns")}
for r in c.execute("SELECT m.id, m.status, m.campaign_id, m.scheduled_at, r.email, coalesce(m.last_error,''), "
                   "(SELECT cr.status||'/'||coalesce(cr.reason,'') FROM confirm_reviews cr WHERE cr.message_id=m.id ORDER BY cr.id DESC LIMIT 1) "
                   "FROM messages m JOIN recipients r ON r.id=m.recipient_id WHERE m.sent_at IS NULL AND m.status IN ('scheduled','sending') "
                   "AND substr(coalesce(m.scheduled_at,''),1,10) < date('now') AND coalesce(m.scheduled_at,'')<>'' ORDER BY m.scheduled_at"):
    print(r[0], r[1], кам.get(r[2]), r[3][:16], r[4], "| карточка:", r[6], "|", r[5][:60])
