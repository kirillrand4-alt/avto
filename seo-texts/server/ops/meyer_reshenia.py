# -*- coding: utf-8 -*-
"""Что владелец нажал сегодня по Meyer: решения карточек (confirm_reviews) за
сутки по кампаниям, статусы их писем; статус кампаний и настройки автоотправки.
Только чтение."""
import sqlite3
from collections import Counter

c = sqlite3.connect(r"C:\sender\sender.db")
c.row_factory = sqlite3.Row
кам = {r["id"]: (r["name"], r["status"]) for r in c.execute("SELECT id, name, status FROM campaigns")}
сч = Counter()
for r in c.execute("SELECT c.campaign_id, c.status, c.reason, c.decided_by, m.status ms, m.scheduled_at, m.last_error FROM confirm_reviews c "
                   "LEFT JOIN messages m ON m.id=c.message_id WHERE c.decided_at>=strftime('%Y-%m-%dT%H:%M:%S','now','-12 hours')"):
    сч[(r["campaign_id"], r["status"], str(r["reason"])[:30], r["decided_by"], r["ms"], str(r["last_error"])[:60])] += 1
for k, v in sorted(сч.items(), key=lambda x: -x[1])[:25]:
    print("  %4d  %s %s" % (v, кам.get(k[0], ("?",))[0][:25], k[1:]))
print("\nкампании:", {k: v for k, v in кам.items() if k in (13, 14, 17, 18)})
for k in ("auto_send", "confirm", "send_limits", "auto_send_divisions", "division_auto"):
    try:
        v = c.execute("SELECT value FROM settings WHERE key=?", (k,)).fetchone()
        if v:
            print("setting", k, "=", str(v[0])[:500])
    except sqlite3.Error as ex:
        print("settings:", ex)
        break

