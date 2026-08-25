# -*- coding: utf-8 -*-
"""Почему автоотправка стоит при 651 готовом письме."""
import sys
import time

sys.path.insert(0, r"C:\sender\sender")
sys.path.insert(0, r"C:\sender")

from datetime import datetime, timezone                       # noqa: E402
from sender.config import Config                              # noqa: E402
from sender.store import Store                                # noqa: E402

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))

print("время сервера UTC: %s" % datetime.now(timezone.utc).isoformat()[:19])
try:
    ок = cfg.sending_window()
    print("окно отправки: дни %s, %s-%s, tz %s"
          % (getattr(ок, "days", "?"), getattr(ок, "start", "?"),
             getattr(ок, "end", "?"), getattr(ок, "tz", "?")))
except Exception as e:  # noqa: BLE001
    print("окно не прочиталось: %s" % e)

print("\n=== ГОТОВНОСТЬ ЯЩИКОВ ===")
живой = None
try:
    from sender.wiring import build_deps
    deps = build_deps(cfg, store, dry_run=True)
    живой = getattr(deps.confirm, "_sender", None)
except Exception as e:  # noqa: BLE001
    print("  deps не собрались: %s" % str(e)[:120])
if живой is not None:
    свободно = 0
    for mb in cfg.mailboxes():
        try:
            r = живой.mailbox_readiness(mb.mailbox_id)
        except Exception as e:  # noqa: BLE001
            print("  %-38s ошибка %s" % (mb.mailbox_id[:38], str(e)[:60]))
            continue
        ост = int(getattr(r, "daily_limit", 0)) - int(getattr(r, "sent_today", 0))
        свободно += max(0, ост)
        print("  %-38s лимит %3d, ушло %3d, свободно %3d%s%s"
              % (mb.mailbox_id[:38], getattr(r, "daily_limit", 0),
                 getattr(r, "sent_today", 0), max(0, ост),
                 "  ПАУЗА" if getattr(r, "paused", False) else "",
                 ("  " + ", ".join(getattr(r, "reasons", ()) or ()))[:60]))
    print("  ---- всего свободных слотов сегодня: %d" % свободно)

print("\n=== ЖИВ ЛИ ЦИКЛ АВТООТПРАВКИ (по журналу панели) ===")
import glob
import io
import os
for п in sorted(glob.glob(r"C:\sender\_ops\panel_*.log"),
                key=lambda x: -os.path.getmtime(x))[:2]:
    print("  %s (обновлён %.1f мин назад)"
          % (os.path.basename(п), (time.time() - os.path.getmtime(п)) / 60.0))
    строки = io.open(п, encoding="utf-8", errors="replace").readlines()[-4000:]
    инт = [с for с in строки if "auto_send" in с or "автоотправ" in с]
    for с in инт[-8:]:
        print("    %s" % с.rstrip()[:170])
    if not инт:
        print("    (строк про автоотправку нет)")
