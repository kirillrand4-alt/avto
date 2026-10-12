# -*- coding: utf-8 -*-
"""Что сейчас в стоп-листе по ИНН: причины, источники, сколько чего."""
import sys
sys.path.insert(0, r"C:\sender")
from sender.store import Store                                  # noqa: E402

store = Store(r"C:\sender\sender.db")
with store._lock:
    c = store._conn
    кол = [x[1] for x in c.execute("PRAGMA table_info(suppression)")]
    print("колонки suppression: %s" % ", ".join(кол))
    print("")
    print("--- по области действия ---")
    for р in c.execute("SELECT scope, COUNT(*) n FROM suppression "
                       " GROUP BY 1 ORDER BY 2 DESC"):
        print("   %-10s %6d" % (р["scope"], р["n"]))
    print("")
    print("--- scope=inn: причины ---")
    for р in c.execute("SELECT COALESCE(reason,'(пусто)') r, COUNT(*) n, "
                       "       MIN(created_at) п, MAX(created_at) к "
                       "  FROM suppression WHERE scope='inn' "
                       " GROUP BY 1 ORDER BY 2 DESC"):
        print("   %-24s %6d   с %s по %s"
              % (str(р["r"])[:24], р["n"], str(р["п"])[:10], str(р["к"])[:10]))
    print("")
    print("--- scope=inn: источники ---")
    for р in c.execute("SELECT COALESCE(source,'(пусто)') s, COUNT(*) n "
                       "  FROM suppression WHERE scope='inn' "
                       " GROUP BY 1 ORDER BY 2 DESC LIMIT 12"):
        print("   %-34s %6d" % (str(р["s"])[:34], р["n"]))
    print("")
    print("--- примеры строк scope=inn ---")
    for р in c.execute("SELECT * FROM suppression WHERE scope='inn' "
                       " ORDER BY id DESC LIMIT 5"):
        print("   " + "; ".join("%s=%s" % (k, str(р[k])[:40])
                                for k in кол if р[k] not in (None, "")))
print("")
print("=" * 74)
print("=== СОСТАВ СТОП-ЛИСТА ПО ИНН ===")
