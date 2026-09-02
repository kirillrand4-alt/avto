# -*- coding: utf-8 -*-
"""Только чтение: почему отправка встала. Важное в конце."""
import datetime as dt
import sqlite3
import sys

sys.path.insert(0, r"C:\sender")
from sender.config import Config              # noqa: E402
from sender.store import Store                # noqa: E402
import sender.gates as G                      # noqa: E402

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
c = sqlite3.connect("file:C:/sender/sender.db?mode=ro", uri=True)
c.row_factory = sqlite3.Row
сейчас = dt.datetime.now()
у = сейчас.replace(hour=0, minute=0, second=0).isoformat()

print("=== СОБЫТИЯ ЗА СЕГОДНЯ ===")
for р in c.execute("SELECT event_type, COUNT(*) k, MAX(event_ts) посл FROM events"
                   " WHERE event_ts>=? GROUP BY event_type ORDER BY k DESC", (у,)):
    print("  %-16s %4d  последнее %s" % (р["event_type"], р["k"],
                                         str(р["посл"])[11:19]))

print("\n=== ДВИГАЛИСЬ ЛИ ПИСЬМА (updated_at) ===")
for р in c.execute("SELECT substr(updated_at,12,5) мин, COUNT(*) k FROM messages"
                   " WHERE campaign_id=12 AND updated_at>=?"
                   " GROUP BY мин ORDER BY мин DESC LIMIT 8",
                   ((сейчас - dt.timedelta(minutes=25)).isoformat(),)):
    print("  %s  %d писем" % (р["мин"], р["k"]))

print("\n=== ЗАСЛОНЫ ===")
g = G.Gates(cfg, store)
гл = g.check_global()
print("  глобальный: tripped=%s причина=%s значение=%s"
      % (гл.tripped, getattr(гл, "reason", None), getattr(гл, "value", None)))
закр = []
for m in cfg.get("mailboxes", []):
    if str(m.get("division")) != "meyer":
        continue
    d = g.check_mailbox(m["mailbox_id"])
    if d.tripped:
        закр.append((m["mailbox_id"], getattr(d, "reason", ""), getattr(d, "value", "")))
print("  закрытых meyer-ящиков: %d" % len(закр))
for mid, р2, v in закр:
    print("    %-34s %s %s" % (mid, str(р2)[:34], v))

print("\n=== ПОСЛЕДНИЕ ОТПРАВКИ ===")
for р in c.execute("SELECT sent_at, mailbox_id, campaign_id FROM messages"
                   " WHERE status='sent' ORDER BY sent_at DESC LIMIT 4"):
    print("  %s | %-34s | кампания %s" % (str(р["sent_at"])[11:19], р["mailbox_id"],
                                          р["campaign_id"]))
print("  сейчас %s" % сейчас.strftime("%H:%M:%S"))

print("\n=== ЗАВИСШИЕ В sending ===")
for р in c.execute("SELECT id, campaign_id, mailbox_id, claimed_at FROM messages"
                   " WHERE status='sending'"):
    print("  msg#%s кампания %s ящик=%s взято %s"
          % (р["id"], р["campaign_id"], р["mailbox_id"], str(р["claimed_at"])[11:19]))
