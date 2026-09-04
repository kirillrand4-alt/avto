# -*- coding: utf-8 -*-
"""Только чтение: пришли ли вердикты по оставшимся адресам партии 13."""
import sqlite3

c = sqlite3.connect("file:C:/sender/sender.db?mode=ro", uri=True)
c.row_factory = sqlite3.Row
ждут = [str(р["email"]).lower() for р in c.execute(
    "SELECT email FROM confirm_reviews WHERE campaign_id=13 AND status='pending'")]
вердикт = {str(р["e"]): (р["verdict"], р["ts"]) for р in c.execute(
    "SELECT LOWER(email) e, verdict, ts FROM addr_probe")}
раскл, свежие = {}, 0
for а in ждут:
    в, ts = вердикт.get(а, (None, None))
    раскл[str(в)] = раскл.get(str(в), 0) + 1
    if ts and str(ts) >= "2026-09-04":
        свежие += 1
print("ждут решения: %d" % len(ждут))
for в, n in sorted(раскл.items(), key=lambda x: -x[1]):
    print("  %-16s %d" % (в, n))
print("  вердиктов, полученных сегодня: %d" % свежие)

print("\n=== ОБЩЕЕ СОСТОЯНИЕ ПАРТИИ 13 ===")
for р in c.execute("SELECT status, COUNT(*) k FROM confirm_reviews"
                   " WHERE campaign_id=13 GROUP BY status"):
    print("  решения %-12s %d" % (р["status"], р["k"]))
for р in c.execute("SELECT status, COUNT(*) k FROM messages"
                   " WHERE campaign_id=13 GROUP BY status"):
    print("  письма  %-12s %d" % (р["status"], р["k"]))
print("\n  всего строк в addr_probe: %d"
      % c.execute("SELECT COUNT(*) FROM addr_probe").fetchone()[0])
print("  из них записано сегодня: %d"
      % c.execute("SELECT COUNT(*) FROM addr_probe WHERE ts>='2026-09-04'").fetchone()[0])
