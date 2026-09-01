# -*- coding: utf-8 -*-
"""Только чтение: уйдут ли 597 запланированных писем и что их держит."""
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

print("=== РУБИЛЬНИКИ ===")
for к in ("orchestrator.active_campaigns", "orchestrator.send_batch",
          "service.dry_run", "confirm.live_send", "confirm.enabled",
          "window.start", "window.end", "sending.enabled", "orchestrator.enabled",
          "auto_send.enabled"):
    try:
        print("  %-34s = %r" % (к, cfg.get(к)))
    except Exception as ex:
        print("  %-34s ! %s" % (к, str(ex)[:40]))

print("\n=== ОКНО ОТПРАВКИ ===")
try:
    w = cfg.sending_window()
    print("  конфиг: %s %s-%s дни %s" % (w.tz, w.start, w.end, list(w.days)))
except Exception as ex:
    print("  ", str(ex)[:80])
try:
    ov = store.get_setting("sending_window")
    print("  переопределение из панели: %r" % ov)
except Exception as ex:
    print("  переопределение: %s" % str(ex)[:60])
print("  сейчас на сервере: %s" % datetime.now().strftime("%Y-%m-%d %H:%M:%S (%A)"))

print("\n=== ГОТОВНОСТЬ ЯЩИКОВ ПРЯМО СЕЙЧАС ===")
gates = G.Gates(cfg, store)
snd = S.Sender(cfg, store, Suppression(store), gates)
готовы, нет = [], {}
for mb in cfg.mailboxes():
    r = snd.mailbox_readiness(mb.mailbox_id)
    if r.ready:
        готовы.append((mb.mailbox_id, r.daily_limit, r.sent_today))
    else:
        нет[",".join(r.reasons)] = нет.get(",".join(r.reasons), 0) + 1
print("  ГОТОВЫ отправлять сейчас: %d" % len(готовы))
for m, l, st in готовы[:20]:
    print("     %-40s лимит %s, сегодня %s" % (m[:40], l, st))
print("  не готовы, по причинам:")
for k, v in sorted(нет.items(), key=lambda x: -x[1]):
    print("     %-46s %d" % (k, v))

print("\n=== ИТОГ ===")
n = store  # noqa
import sqlite3
s = sqlite3.connect("file:C:/sender/sender.db?mode=ro", uri=True)
s.row_factory = sqlite3.Row
сч = s.execute("SELECT COUNT(*) n FROM messages WHERE status='scheduled'").fetchone()["n"]
бл = s.execute("SELECT COUNT(*) n FROM messages WHERE status='scheduled'"
               " AND scheduled_at <= datetime('now')").fetchone()["n"]
print("  запланировано писем: %d, из них время уже подошло: %d" % (сч, бл))
сум = sum(l - st for _, l, st in готовы)
print("  суммарная дневная ёмкость готовых ящиков: %d писем" % сум)
