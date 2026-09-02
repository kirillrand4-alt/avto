# -*- coding: utf-8 -*-
"""Только чтение: за что снимаются письма партии."""
import datetime as dt
import sqlite3

c = sqlite3.connect("file:C:/sender/sender.db?mode=ro", uri=True)
c.row_factory = sqlite3.Row
print("=== ПРИЧИНЫ СКИПОВ ПО КАМПАНИИ 12 ===")
for р in c.execute("SELECT last_error, COUNT(*) k FROM messages WHERE campaign_id=12"
                   " AND status='skipped' GROUP BY last_error ORDER BY k DESC"):
    print("  %3d | %s" % (р["k"], str(р["last_error"])[:96]))

print("\n=== ПРИМЕРЫ КОГО СНЯЛИ ===")
for р in c.execute("SELECT r.email, r.company_name, m.last_error FROM messages m"
                   " JOIN recipients r ON r.id=m.recipient_id"
                   " WHERE m.campaign_id=12 AND m.status='skipped' LIMIT 12"):
    print("  %-34s %-22s %s" % (р["email"][:34], str(р["company_name"])[:22],
                                str(р["last_error"])[:46]))

print("\n=== ИТОГ ПО ПАРТИИ %s ===" % dt.datetime.now().strftime("%H:%M:%S"))
for р in c.execute("SELECT status, COUNT(*) k FROM messages WHERE campaign_id=12"
                   " GROUP BY status"):
    print("  %-14s %d" % (р["status"], р["k"]))
