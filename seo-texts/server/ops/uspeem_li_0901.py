# -*- coding: utf-8 -*-
"""Только чтение: успеет ли очередь уйти до закрытия окна."""
import sqlite3
import sys
from datetime import datetime, timezone

sys.path.insert(0, r"C:\sender")
from sender.config import Config          # noqa: E402
from sender.store import Store            # noqa: E402
from sender.suppression import Suppression  # noqa: E402
import sender.sender as S                 # noqa: E402
import sender.gates as G                  # noqa: E402

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
snd = S.Sender(cfg, store, Suppression(store), G.Gates(cfg, store))
s = sqlite3.connect("file:C:/sender/sender.db?mode=ro", uri=True)
s.row_factory = sqlite3.Row

print("=== ТЕМП ПО 5 МИНУТ ПОСЛЕ СНЯТИЯ ПАУЗЫ ===")
for р in s.execute("SELECT substr(created_at,1,15) м, COUNT(*) n FROM events"
                   " WHERE event_type='sent' AND created_at >= '2026-09-01T06:30'"
                   " GROUP BY м ORDER BY м"):
    print("  %s0  %d" % (р["м"], р["n"]))

print("\n=== ЁМКОСТЬ ПО ЯЩИКАМ MEYER ===")
ост = 0
for mb in cfg.mailboxes():
    if getattr(mb, "division", "") != "meyer":
        continue
    r = snd.mailbox_readiness(mb.mailbox_id)
    if r.ready:
        св = max(0, r.daily_limit - r.sent_today)
        ост += св
        print("  %-38s свободно %3d (лимит %d, ушло %d)"
              % (mb.mailbox_id[:38], св, r.daily_limit, r.sent_today))

print("\n=== ИТОГ ===")
now_iso = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()
оч = s.execute("SELECT COUNT(*) n FROM messages WHERE status='scheduled'").fetchone()["n"]
созр = s.execute("SELECT COUNT(*) n FROM messages m WHERE m.status='scheduled'"
                 " AND m.scheduled_at <= ?"
                 " AND (SELECT cr.status FROM confirm_reviews cr WHERE cr.message_id=m.id"
                 "      ORDER BY cr.id DESC LIMIT 1) IN ('approved','edited')",
                 (now_iso,)).fetchone()["n"]
за15 = s.execute("SELECT COUNT(*) n FROM events WHERE event_type='sent'"
                 " AND created_at >= datetime('now','-15 minute')").fetchone()["n"]
сег = s.execute("SELECT COUNT(*) n FROM events WHERE event_type='sent'"
                " AND created_at >= date('now')").fetchone()["n"]
мск = datetime.now()
до_конца = (14 * 60) - (мск.hour * 60 + мск.minute)
print("  сейчас мск %s, до закрытия окна %d мин" % (мск.strftime("%H:%M"), до_конца))
print("  в очереди %d, созревших и одобренных %d" % (оч, созр))
print("  отправлено сегодня всего: %d" % сег)
print("  темп за 15 минут: %d писем (%.1f в минуту)" % (за15, за15 / 15.0))
print("  СВОБОДНАЯ ЁМКОСТЬ meyer: %d" % ост)
if за15:
    надо = оч / (за15 / 15.0)
    print("  при этом темпе очередь ушла бы за %.0f мин" % надо)
print("\n  ПОТОЛОК СЕГОДНЯ = min(ёмкость %d, темп x время %d) = %d"
      % (ост, int((за15 / 15.0) * до_конца) if за15 else 0,
         min(ост, int((за15 / 15.0) * до_конца) if за15 else 0)))
print("  ОСТАНЕТСЯ НА ЗАВТРА: примерно %d"
      % max(0, оч - min(ост, int((за15 / 15.0) * до_конца) if за15 else 0)))
