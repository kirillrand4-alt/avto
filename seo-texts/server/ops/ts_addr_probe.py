# -*- coding: utf-8 -*-
"""Можно ли верить ts в addr_probe: разброс меток времени."""
import sys
from collections import Counter
sys.path.insert(0, r"C:\sender")
from sender.store import Store                                  # noqa: E402

store = Store(r"C:\sender\sender.db")
with store._lock:
    кол = [c[1] for c in store._conn.execute("PRAGMA table_info(addr_probe)")]
    n = store._conn.execute("SELECT COUNT(*) FROM addr_probe").fetchone()[0]
    р = store._conn.execute(
        "SELECT MIN(ts) a, MAX(ts) b, COUNT(DISTINCT ts) c, "
        "       COUNT(DISTINCT substr(ts,1,10)) d FROM addr_probe").fetchone()
    дни = Counter()
    for x in store._conn.execute(
            "SELECT substr(ts,1,10) d, COUNT(*) n FROM addr_probe GROUP BY 1 "
            "ORDER BY 1"):
        дни[str(x["d"])] = int(x["n"])
print("колонки: %s" % ", ".join(кол))
print("строк: %d" % n)
print("ts: от %s до %s" % (р["a"], р["b"]))
print("разных значений ts: %d; разных дат: %d" % (р["c"], р["d"]))
print("")
print("--- строк по датам ts ---")
for д in sorted(дни)[-10:]:
    print("   %s  %6d" % (д, дни[д]))
print("")
print("=" * 70)
print("=== ВЕРИТЬ ЛИ ts ===")
if р["d"] and int(р["d"]) <= 2:
    print("ВСЕ метки времени в одной-двух датах - ts переписан оптом,")
    print("и по нему нельзя судить, когда адрес проверяли на самом деле.")
else:
    print("метки распределены по датам - ts осмысленный")
