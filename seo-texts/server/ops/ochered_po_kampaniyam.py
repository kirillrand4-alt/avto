# -*- coding: utf-8 -*-
"""Письма в работе по кампаниям: scheduled/sending (автоотправка) и pending_review (ждут подтверждения),
плюс отправлено за 7 дней. Только чтение."""
import sqlite3
c = sqlite3.connect(r"C:\sender\sender.db", timeout=90)
for cid, имя, sch, pr, s7 in c.execute(
        "SELECT c.id, c.name, sum(m.status IN ('scheduled','sending')), sum(m.status='pending_review'), "
        "sum(m.status='sent' AND m.sent_at >= datetime('now','-7 days')) FROM messages m JOIN campaigns c ON c.id=m.campaign_id "
        "GROUP BY c.id HAVING sum(m.status IN ('scheduled','sending','pending_review')) > 0 OR sum(m.status='sent' AND m.sent_at >= datetime('now','-7 days')) > 0 ORDER BY c.id"):
    print("%3d %-30s в автоотправке %5d | ждут подтверждения %5d | ушло за 7 дн %5d" % (cid, имя[:30], sch or 0, pr or 0, s7 or 0))
