# -*- coding: utf-8 -*-
"""Как часто генерация упирается в «database is locked» и идёт ли она."""
import io
import json
import os
т = io.open(r"C:\sender\_ops\gen-rossiya-9000.log", encoding="utf-8",
            errors="replace").read()
кусок = т.rsplit("==== ЗАПУСК", 1)[-1]
print("блокировок базы после запуска: %d" % кусок.count("database is locked"))
for база in ("obzvon", "enrich.db", "sender.db"):
    print("   упоминаний %s рядом с блокировкой: %d" % (база, кусок.count(база)))
ж = r"C:\sender\_ops\gen-rossiya-9000.jsonl"
n = sum(1 for _ in io.open(ж, encoding="utf-8")) if os.path.exists(ж) else 0
print("строк журнала генерации: %d" % n)
import sqlite3
for п in (r"C:\sender\obzvon-index.db", r"C:\sender\enrich.db"):
    c = sqlite3.connect(п, timeout=5)
    print("%s: journal_mode=%s" % (os.path.basename(п),
                                   c.execute("PRAGMA journal_mode").fetchone()[0]))
    c.close()
print("=== БЛОКИРОВКИ ===")
