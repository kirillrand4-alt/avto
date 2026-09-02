# -*- coding: utf-8 -*-
"""Только чтение: как устроена автоотправка панели и в каком она состоянии."""
import io
import os
import re
import sqlite3
import sys

sys.path.insert(0, r"C:\sender")
from sender.config import Config  # noqa: E402
from sender.store import Store    # noqa: E402

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))

print("=== КОД АВТООТПРАВКИ В ПАНЕЛИ ===")
п = r"C:\sender\sender\app.py"
т = io.open(п, encoding="utf-8", errors="replace").read()
лн = т.splitlines()
инт = []
for м in re.finditer(r"(?i)(avtootpravk|автоотправк|autosend|auto_send|"
                     r"tick\(|run_once|orchestr)", т):
    н = т[:м.start()].count("\n")
    с = лн[н].strip()
    if с.startswith("#") or not с:
        continue
    инт.append((н + 1, с))
видел = set()
for н, с in инт:
    к = с[:60]
    if к in видел:
        continue
    видел.add(к)
    print("  app.py:%d  %s" % (н, с[:104]))

print("\n=== НАСТРОЙКИ В БАЗЕ ===")
c = sqlite3.connect("file:C:/sender/sender.db?mode=ro", uri=True)
c.row_factory = sqlite3.Row
таб = [r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'"
                               " AND name LIKE '%setting%'")]
print("  таблицы настроек: %s" % таб)
for т2 in таб:
    кол = [r["name"] for r in c.execute("PRAGMA table_info(%s)" % т2)]
    for р in c.execute("SELECT * FROM %s LIMIT 40" % т2):
        стр = " | ".join("%s=%s" % (k, str(р[k])[:44]) for k in кол)
        if any(s in стр.lower() for s in ("send", "otprav", "auto", "pause",
                                          "stop", "tick", "orchestr", "limit")):
            print("    " + стр[:150])
