# -*- coding: utf-8 -*-
"""Что у КЦ в очереди: pending-карточки КЦ и письма КЦ в автоотправке (не отправленные)."""
import sqlite3
c = sqlite3.connect(r"C:\sender\sender.db", timeout=60)
кц = [i for i, n in c.execute("SELECT id, name FROM campaigns") if "кц" in n.lower() or "компрессор" in n.lower()]
м = ",".join(map(str, кц)) or "0"
print("кампании КЦ:", [tuple(r) for r in c.execute("SELECT id, name FROM campaigns WHERE id IN (%s)" % м)])
print("pending карточек КЦ:", c.execute("SELECT COUNT(*) FROM confirm_reviews WHERE status='pending' AND campaign_id IN (%s)" % м).fetchone()[0])
print("письма КЦ по статусам (не sent):", [tuple(r) for r in c.execute("SELECT status, COUNT(*) FROM messages WHERE campaign_id IN (%s) AND status!='sent' GROUP BY 1" % м)])
print("последняя отправка КЦ:", c.execute("SELECT MAX(sent_at) FROM messages WHERE campaign_id IN (%s) AND status='sent'" % м).fetchone()[0])
