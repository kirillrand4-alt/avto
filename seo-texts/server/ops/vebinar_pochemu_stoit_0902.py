# -*- coding: utf-8 -*-
"""Только чтение: почему с полуночи не ушло ни одного письма."""
import datetime as dt
import glob
import io
import os
import sqlite3
import sys

sys.path.insert(0, r"C:\sender")
from sender.config import Config  # noqa: E402
from sender.store import Store    # noqa: E402
import sender.gates as G          # noqa: E402

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
c = sqlite3.connect("file:C:/sender/sender.db?mode=ro", uri=True)
c.row_factory = sqlite3.Row

print("\n=== ЛОГ СЛУЖБЫ, ХВОСТ ===")
кандидаты = []
for шаб in (r"C:\sender\logs\*.log", r"C:\sender\*.log", r"C:\sender\log\*.log"):
    кандидаты.extend(glob.glob(шаб))
кандидаты.sort(key=lambda п: os.path.getmtime(п), reverse=True)
print("  файлов логов: %d" % len(кандидаты))
for п in кандидаты[:2]:
    м = dt.datetime.fromtimestamp(os.path.getmtime(п))
    print("\n  --- %s (изменён %s) ---" % (os.path.basename(п), м.strftime("%H:%M")))
    try:
        строки = io.open(п, encoding="utf-8", errors="replace").read().splitlines()
        for л in строки[-14:]:
            print("    " + л[:112])
    except Exception as ex:
        print("    не прочитать: %s" % str(ex)[:80])

print("=== ПОСЛЕДНИЕ ОТПРАВКИ ===")
for р in c.execute("SELECT sent_at, mailbox_id, campaign_id FROM messages"
                   " WHERE status='sent' ORDER BY sent_at DESC LIMIT 5"):
    print("  %s | %s | кампания %s" % (р["sent_at"], р["mailbox_id"], р["campaign_id"]))

print("\n=== ЗАВИСШИЕ В 'sending' ===")
for р in c.execute("SELECT id, campaign_id, mailbox_id, claimed_at, updated_at"
                   " FROM messages WHERE status='sending'"):
    print("  msg#%s кампания %s ящик=%s взято=%s"
          % (р["id"], р["campaign_id"], р["mailbox_id"], р["claimed_at"]))

print("\n=== ГЛОБАЛЬНЫЕ ЗАСЛОНЫ ===")
g = G.Gates(cfg, store)
гл = g.check_global()
print("  глобальный гейт: tripped=%s причина=%s"
      % (гл.tripped, getattr(гл, "reason", None)))
for к in ("service.autosend", "orchestrator.enabled", "service.paused",
          "kill_switch", "service.dry_run", "confirm.live_send"):
    print("  %-24s %s" % (к, cfg.get(к, "нет ключа")))
try:
    for к in ("autosend", "avtootpravka", "orchestrator_enabled"):
        print("  настройка «%s» в базе: %s" % (к, store.get_setting(к, None)))
except Exception as ex:
    print("  get_setting: %s" % str(ex)[:90])

