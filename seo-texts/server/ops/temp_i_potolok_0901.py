# -*- coding: utf-8 -*-
"""Только чтение: что ограничивает темп отправки сейчас."""
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

print("=== ЯЩИКИ MEYER: СКОЛЬКО УЖЕ ОТПРАВИЛИ И СКОЛЬКО МОГУТ ===")
ост = 0
for mb in cfg.mailboxes():
    if getattr(mb, "division", "") != "meyer":
        continue
    r = snd.mailbox_readiness(mb.mailbox_id)
    св = max(0, r.daily_limit - r.sent_today) if r.ready else 0
    ост += св
    print("  %-38s лимит %3d, сегодня %3d, осталось %3d  %s"
          % (mb.mailbox_id[:38], r.daily_limit, r.sent_today, св,
             "" if r.ready else "(" + ",".join(r.reasons) + ")"))

print("\n=== ТЕМП ЗА ПОСЛЕДНИЕ 30 МИНУТ ===")
for р in s.execute("SELECT substr(created_at,1,16) м, COUNT(*) n FROM events"
                   " WHERE event_type='sent' AND created_at >= datetime('now','-40 minute')"
                   " GROUP BY м ORDER BY м"):
    print("  %s  %d" % (р["м"], р["n"]))

print("\n=== ИТОГ ===")
now_iso = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()
созр = s.execute("SELECT COUNT(*) n FROM messages WHERE status='scheduled'"
                 " AND scheduled_at <= ?", (now_iso,)).fetchone()["n"]
одобр = s.execute(
    "SELECT COUNT(*) n FROM messages m WHERE m.status='scheduled'"
    " AND m.scheduled_at <= ?"
    " AND (SELECT cr.status FROM confirm_reviews cr WHERE cr.message_id=m.id"
    "      ORDER BY cr.id DESC LIMIT 1) IN ('approved','edited')", (now_iso,)).fetchone()["n"]
print("  созрело по времени                : %d" % созр)
print("  из них с одобренной карточкой     : %d  <- только эти оркестратор возьмёт" % одобр)
print("  свободная ёмкость meyer на сегодня: %d" % ост)
print("  отправлено за час                 : %d"
      % s.execute("SELECT COUNT(*) n FROM events WHERE event_type='sent'"
                  " AND created_at >= datetime('now','-1 hour')").fetchone()["n"])
print("  send_batch за тик                 : %s" % cfg.get("orchestrator.send_batch"))
print("  сейчас мск %s, окно до 14:00" % datetime.now().strftime("%H:%M"))
