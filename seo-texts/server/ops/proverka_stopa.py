# -*- coding: utf-8 -*-
"""Правда ли, что ни одна компания книг не в стоп-листе."""
import glob
import io
import json
import sys

sys.path.insert(0, r"C:\sender")
from sender.store import Store                                  # noqa: E402

store = Store(r"C:\sender\sender.db")
with store._lock:
    c = store._conn
    есть = [р["name"] for р in c.execute(
        "SELECT name FROM sqlite_master WHERE type='table' "
        "AND name LIKE '%suppress%'")]
    print("таблицы: %s" % есть)
    for т in есть:
        кол = [р["name"] for р in c.execute("PRAGMA table_info(%s)" % т)]
        print("   %s: %s" % (т, ", ".join(кол)))
        for р in c.execute("SELECT scope, COUNT(*) n FROM %s GROUP BY scope" % т):
            print("      scope=%-8s %6d" % (р["scope"], р["n"]))
        for р in c.execute("SELECT scope, value, reason FROM %s LIMIT 4" % т):
            print("      пример: %s | %s | %s"
                  % (р["scope"], str(р["value"])[:30], str(р["reason"])[:40]))

инны = set()
for п in sorted(glob.glob(r"C:\sender\server\ops\knigi2_*.json")):
    for к in (json.load(io.open(п, encoding="utf-8")).get("компании") or []):
        инны.add(к["inn"])
сп = list(инны)
совпало = 0
with store._lock:
    c = store._conn
    for н in range(0, len(сп), 400):
        к_ = сп[н:н + 400]
        м = ",".join("?" * len(к_))
        совпало += c.execute(
            "SELECT COUNT(*) FROM suppression WHERE scope='inn' "
            "AND value IN (" + м + ")", к_).fetchone()[0]
print("")
print("ИНН книг: %d, из них в стоп-листе: %d" % (len(инны), совпало))
