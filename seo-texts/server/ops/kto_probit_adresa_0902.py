# -*- coding: utf-8 -*-
"""Только чтение: кто и где проверяет адреса."""
import datetime as dt
import inspect
import io
import re
import sqlite3
import sys

sys.path.insert(0, r"C:\sender")
from sender.config import Config  # noqa: E402
from sender.store import Store    # noqa: E402

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))

print("=== probe_sync: назначение ===")
т = io.open(r"C:\sender\sender\probe_sync.py", encoding="utf-8",
            errors="replace").read()
print("  " + "\n  ".join(т.splitlines()[1:16]))

print("\n=== ГДЕ УПОМИНАЕТСЯ ВНЕШНИЙ СЕРВЕР / VPS ===")
for ф in (r"C:\sender\sender\probe_sync.py", r"C:\sender\sender\addr_probe.py"):
    s2 = io.open(ф, encoding="utf-8", errors="replace").read()
    лн = s2.splitlines()
    for м in re.finditer(r"(?i)(vps|внешн|http[s]?://|url|host|endpoint|drop)", s2):
        н = s2[:м.start()].count("\n")
        с = лн[н].strip()
        if с.startswith("#") or len(с) < 8:
            continue
        print("  %-16s %s" % (ф.split("\\")[-1], с[:92]))

print("\n=== НАСТРОЙКИ ПРОБЫ ===")
for к in ("addr_probe", "probe", "probe_sync"):
    зн = cfg.get(к, None)
    if зн is not None:
        print("  %s = %s" % (к, str(dict(зн) if hasattr(зн, "keys") else зн)[:220]))
print("  addr_probe_enabled в панели: %s" % store.get_setting("addr_probe_enabled", None))

c = sqlite3.connect("file:C:/sender/sender.db?mode=ro", uri=True)
c.row_factory = sqlite3.Row
print("\n=== ТАБЛИЦА addr_probe ===")
кол = [r["name"] for r in c.execute("PRAGMA table_info(addr_probe)")]
print("  %s" % ", ".join(кол))
print("  строк: %d" % c.execute("SELECT COUNT(*) FROM addr_probe").fetchone()[0])
for р in c.execute("SELECT verdict, COUNT(*) n, MAX(checked_at) посл FROM addr_probe"
                   " GROUP BY verdict ORDER BY n DESC LIMIT 8"):
    print("  %-16s %6d  последняя проверка %s"
          % (str(р["verdict"]), р["n"], str(р["посл"])[:19]))
