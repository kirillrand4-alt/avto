# -*- coding: utf-8 -*-
"""Только чтение: почему сейчас нет новых отправок."""
import sqlite3
import subprocess
import sys
from collections import Counter
from datetime import datetime

sys.path.insert(0, r"C:\sender")
from sender.config import Config          # noqa: E402
from sender.store import Store            # noqa: E402
from sender.suppression import Suppression  # noqa: E402
import sender.sender as S                 # noqa: E402
import sender.gates as G                  # noqa: E402

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
gates = G.Gates(cfg, store)
snd = S.Sender(cfg, store, Suppression(store), gates)
s = sqlite3.connect("file:C:/sender/sender.db?mode=ro", uri=True)
s.row_factory = sqlite3.Row

print("=== ВРЕМЯ И ОКНО ===")
print("  сейчас на сервере: %s" % datetime.now().strftime("%Y-%m-%d %H:%M:%S (%A)"))
print("  окно из панели   : %s" % store.get_setting("sending_window"))
try:
    print("  в окне ли сейчас : %s" % snd._within_window(datetime.now().astimezone()))
except Exception as ex:
    print("  проверка окна    : %s" % str(ex)[:70])

print("\n=== СЛУЖБА ===")
try:
    r = subprocess.run(["powershell", "-NoProfile", "-Command",
                        "Get-Service SenderPanel | Select-Object Status,Name | Format-List"],
                       capture_output=True, text=True, timeout=60)
    print("  " + (r.stdout.strip()[:200] or "?"))
except Exception as ex:
    print("  ", str(ex)[:80])

print("\n=== ОТПРАВКИ ЗА ПОСЛЕДНИЕ ЧАСЫ (события sent) ===")
for р in s.execute("SELECT substr(created_at,1,13) ч, COUNT(*) n FROM events"
                   " WHERE event_type='sent' AND created_at >= datetime('now','-12 hour')"
                   " GROUP BY ч ORDER BY ч DESC LIMIT 12"):
    print("  %s  %d" % (р["ч"], р["n"]))
п = s.execute("SELECT MAX(created_at) m FROM events WHERE event_type='sent'").fetchone()
print("  последнее событие sent: %s" % п["m"])

print("\n=== ГЛОБАЛЬНЫЕ ГЕЙТЫ ===")
for имя, ф in (("check_global", gates.check_global), ("check_otkaz_vsego", gates.check_otkaz_vsego)):
    try:
        d = ф()
        print("  %-20s tripped=%s %s" % (имя, getattr(d, "tripped", "?"),
                                         str(getattr(d, "reason", ""))[:70]))
    except Exception as ex:
        print("  %-20s ошибка: %s" % (имя, str(ex)[:60]))

print("\n=== ГОТОВНОСТЬ ЯЩИКОВ ===")
c = Counter()
для_meyer = 0
for mb in cfg.mailboxes():
    r = snd.mailbox_readiness(mb.mailbox_id)
    ключ = "ГОТОВ" if r.ready else ",".join(r.reasons)
    c[ключ] += 1
    if r.ready and getattr(mb, "division", "") == "meyer":
        для_meyer += 1
for k, v in c.most_common():
    print("  %-46s %d" % (k, v))
print("  готовых meyer-ящиков: %d" % для_meyer)

print("\n=== ИТОГ: ОЧЕРЕДЬ ===")
for р in s.execute("SELECT status, COUNT(*) n FROM messages"
                   " WHERE status IN ('scheduled','sending','pending_review')"
                   " GROUP BY status"):
    print("  %-16s %d" % (р["status"], р["n"]))
готово = s.execute("SELECT COUNT(*) n FROM messages WHERE status='scheduled'"
                   " AND scheduled_at <= datetime('now')").fetchone()["n"]
print("  из scheduled время подошло у: %d" % готово)
