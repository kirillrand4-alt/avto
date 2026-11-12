# -*- coding: utf-8 -*-
"""Найти, кому мы писали из компании, приславшей входящее без привязки: по названию в панелях карточек и получателях.
   naiti_kompaniyu_vhodyashego.py <кусок названия> [ящик]. Только чтение."""
import sqlite3, sys
кус = sys.argv[1]; ящ = sys.argv[2] if len(sys.argv) > 2 else ""
c = sqlite3.connect("file:C:\\sender\\sender.db?mode=ro", uri=True)
р = c.execute("SELECT cr.id, cr.campaign_id, cr.status, cr.inn, cr.email, m.mailbox_id, m.status, m.sent_at FROM confirm_reviews cr LEFT JOIN messages m ON m.id=cr.message_id "
              "WHERE cr.panel_json LIKE ? ORDER BY cr.id DESC LIMIT 10", ("%" + кус + "%",)).fetchall()
print("карточки с названием:", р)
кол = [x[1] for x in c.execute("PRAGMA table_info(recipients)")]
поле = next((к for к in ("company", "company_name", "name", "org") if к in кол), None)
if поле:
    print("получатели:", c.execute("SELECT r.id, r.inn, r.email, m.campaign_id, m.status, m.sent_at, m.mailbox_id FROM recipients r LEFT JOIN messages m ON m.recipient_id=r.id WHERE r.%s LIKE ? LIMIT 10" % поле, ("%" + кус + "%",)).fetchall())
else: print("колонки recipients:", кол)
if ящ:
    print("письма ящика с телом, где название:", c.execute("SELECT id, campaign_id, status, sent_at FROM messages WHERE mailbox_id=? AND body_rendered LIKE ? LIMIT 5", (ящ, "%" + кус + "%")).fetchall())
