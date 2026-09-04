# -*- coding: utf-8 -*-
"""Один проход цикла автоотправки вручную, тем же кодом, что и панель.

За проход уходит не больше batch=10 писем. Это не обход холда: письма
одобрены владельцем и созрели, движок сам решает, кому и с какого ящика.

argv: проба | делать
"""
import datetime as dt
import sys

sys.path.insert(0, r"C:\sender")
from sender.config import Config    # noqa: E402
from sender.store import Store      # noqa: E402
import sender.wiring as W           # noqa: E402
import sender.auto_send as A        # noqa: E402

ДЕЛАТЬ = (sys.argv[1] if len(sys.argv) > 1 else "проба") == "делать"
cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
deps = W.build_deps(cfg, store, dry_run=True)
жив = getattr(deps, "live_sender", None)
print("live_sender собран: %s" % (type(жив).__name__ if жив else "НЕТ (None)"))
if жив is not None:
    print("  dry_run у него: %s" % getattr(жив, "dry_run", "?"))

петля = A.AutoSendLoop(store=store, config=cfg, live_sender=жив)
print("цикл: sender есть=%s, включён=%s, крутится=%s"
      % (петля.sender is not None, петля.enabled(), петля.running()))
print("  интервал %s сек, партия %s писем" % (петля.interval, петля.batch))
win = A.window_from(store, cfg)
print("  окно: %s" % win)

if not ДЕЛАТЬ:
    print("\nпроба: проход не выполняю")
    raise SystemExit(0)

print("\n=== ВЫПОЛНЯЮ ОДИН ПРОХОД ===")
итог = петля.tick()
print("  результат: %s" % итог)
print("  last_result: %s" % петля.last_result)
