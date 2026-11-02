# -*- coding: utf-8 -*-
"""Отправлено и ответы (события reply, по message→campaign) по кампаниям за 21 день. Только чтение."""
import sqlite3
c = sqlite3.connect("file:C:\\sender\\sender.db?mode=ro", uri=True, timeout=30)
им = dict(c.execute("SELECT id, name FROM campaigns"))
s = dict(c.execute("SELECT campaign_id, count(*) FROM send_log WHERE outcome='sent' AND ts>=date('now','-21 days') GROUP BY 1"))
o = dict(c.execute("SELECT m.campaign_id, count(DISTINCT e.message_id) FROM events e JOIN messages m ON m.id=e.message_id "
                   "WHERE e.event_type='reply' AND e.event_ts>=date('now','-21 days') GROUP BY 1"))
for k in sorted(s):
    print("%3s %-40s ушло %5d ответов %3d  %.2f%%" % (k, str(им.get(k))[:40], s[k], o.get(k, 0), 100.0 * o.get(k, 0) / s[k]))
