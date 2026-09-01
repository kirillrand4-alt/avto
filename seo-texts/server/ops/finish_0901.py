# -*- coding: utf-8 -*-
"""Только чтение: итог дня и почему a.kozlov простаивает."""
import json
import sqlite3
import sys
from datetime import datetime, timedelta, timezone

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


def iso(м):
    return (datetime.now(timezone.utc).replace(tzinfo=None)
            - timedelta(minutes=м)).isoformat()


print("=== ПОТОЛКИ СЕЙЧАС ===")
v = store.get_setting("send_limits")
if isinstance(v, str) and v:
    v = json.loads(v)
print("  all = %r" % (v or {}).get("all"))
per = (v or {}).get("per_mailbox") or {}
print("  per_mailbox: %d записей" % len(per))
for k in sorted(per):
    if "zerno" in k or "optic" in k or "sort-sys" in k:
        print("     %-38s %s" % (k[:38], per[k]))

print("\n=== a.kozlov@zernosort.ru ПОДРОБНО ===")
r = snd.mailbox_readiness("a.kozlov@zernosort.ru")
print("  ready=%s ramp=%s limit=%s sent_today=%s reasons=%s"
      % (r.ready, r.ramp_day, r.daily_limit, r.sent_today, r.reasons))
try:
    d = G.Gates(cfg, store).check_mailbox("a.kozlov@zernosort.ru")
    print("  гейт ящика: tripped=%s %s" % (d.tripped, str(getattr(d, "reason", ""))[:60]))
except Exception as ex:
    print("  гейт: %s" % str(ex)[:60])

print("\n=== ИТОГ ДНЯ ===")
мск = datetime.now()
сег = s.execute("SELECT COUNT(*) n FROM events WHERE event_type='sent' AND created_at >= ?",
                (datetime.now(timezone.utc).strftime("%Y-%m-%dT00:00:00"),)).fetchone()["n"]
оч = s.execute("SELECT COUNT(*) n FROM messages WHERE status='scheduled'").fetchone()["n"]
n30 = s.execute("SELECT COUNT(*) n FROM events WHERE event_type='sent'"
                " AND created_at >= ?", (iso(30),)).fetchone()["n"]
ост = 0
for mb in cfg.mailboxes():
    if getattr(mb, "division", "") != "meyer":
        continue
    rr = snd.mailbox_readiness(mb.mailbox_id)
    if rr.ready:
        ост += max(0, rr.daily_limit - rr.sent_today)
print("  сейчас мск %s, до закрытия окна %d мин"
      % (мск.strftime("%H:%M"), (14 * 60) - (мск.hour * 60 + мск.minute)))
print("  отправлено сегодня: %d" % сег)
print("  в очереди осталось: %d" % оч)
print("  темп за 30 мин: %d (%.1f/мин)" % (n30, n30 / 30.0))
print("  свободная ёмкость meyer: %d" % ост)
