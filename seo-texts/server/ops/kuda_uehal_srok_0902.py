# -*- coding: utf-8 -*-
"""Только чтение: не перенёс ли цикл срок наших писем в другой день."""
import datetime as dt
import sqlite3
import sys

sys.path.insert(0, r"C:\sender")
from sender.config import Config  # noqa: E402
from sender.store import Store    # noqa: E402
import sender.auto_send as A      # noqa: E402

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
c = sqlite3.connect("file:C:/sender/sender.db?mode=ro", uri=True)
c.row_factory = sqlite3.Row

print("=== СРОКИ ПИСЕМ КАМПАНИИ 12 ===")
for р in c.execute("SELECT scheduled_at, COUNT(*) k FROM messages WHERE campaign_id=12"
                   " GROUP BY scheduled_at ORDER BY scheduled_at"):
    print("  %-32s %d" % (р["scheduled_at"], р["k"]))
print("  сейчас: %s" % dt.datetime.now().isoformat(timespec="seconds"))

print("\n=== СРОКИ КАМПАНИИ 11 (для сравнения) ===")
for р in c.execute("SELECT substr(scheduled_at,1,13) ч, COUNT(*) k FROM messages"
                   " WHERE campaign_id=11 AND status='scheduled'"
                   " GROUP BY ч ORDER BY ч LIMIT 8"):
    print("  %-18s %d" % (р["ч"], р["k"]))

print("\n=== ЗОНА ПОЛУЧАТЕЛЯ У НАШИХ ===")
н = c.execute("SELECT COUNT(*) FROM messages m JOIN recipients r ON r.id=m.recipient_id"
              " WHERE m.campaign_id=12 AND (r.tz IS NULL OR r.tz='')").fetchone()[0]
всего = c.execute("SELECT COUNT(*) FROM messages WHERE campaign_id=12").fetchone()[0]
print("  без часовой зоны: %d из %d" % (н, всего))
for р in c.execute("SELECT r.tz, r.region, COUNT(*) k FROM messages m"
                   " JOIN recipients r ON r.id=m.recipient_id WHERE m.campaign_id=12"
                   " GROUP BY r.tz ORDER BY k DESC LIMIT 6"):
    print("    tz=%-16s регион=%-20s %d" % (str(р["tz"]), str(р["region"])[:20], р["k"]))

print("\n=== ЧТО СКАЖЕТ next_slot ПО НАШЕМУ ПИСЬМУ ===")
р = c.execute("SELECT m.id, m.recipient_id FROM messages m WHERE m.campaign_id=12"
              " LIMIT 1").fetchone()
rec = store.get_recipient(р["recipient_id"])
win = A.window_from(store, cfg)
print("  окно: %s" % str(win)[:160])
try:
    зона = A.recipient_tz_name(rec)
    print("  зона получателя: %s" % зона)
    слот = A.next_slot(dt.datetime.now(dt.timezone.utc), win, зона)
    print("  ближайший слот: %s" % слот)
except Exception as ex:
    print("  ошибка: %s: %s" % (type(ex).__name__, str(ex)[:150]))
