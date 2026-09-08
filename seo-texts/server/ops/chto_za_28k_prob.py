# -*- coding: utf-8 -*-
"""28 тысяч проб за час - это что: SMTP-работник или лёгкая проверка MX?"""
import sys
from collections import Counter
sys.path.insert(0, r"C:\sender")
from sender.store import Store                                  # noqa: E402

store = Store(r"C:\sender\sender.db")
with store._lock:
    кол = [c[1] for c in store._conn.execute("PRAGMA table_info(addr_probe)")]
    print("колонки addr_probe: %s" % ", ".join(кол))
    ист = next((c for c in ("source", "src", "kind") if c in кол), None)
    for окно, вырез in (("за час 09", "-1 hour"), ("за сутки", "-1 day"),
                        ("за неделю", "-7 days")):
        c = Counter()
        for р in store._conn.execute(
                "SELECT %s s, verdict v, COUNT(*) n FROM addr_probe "
                " WHERE ts >= datetime('now',?) GROUP BY %s, verdict"
                % (ист or "'-'", ист or "'-'"), (вырез,)):
            c["%s / %s" % (р["s"], р["v"])] += int(р["n"])
        print("")
        print("--- %s ---" % окно)
        for к, в in c.most_common(8):
            print("   %-46s %6d" % (к, в))
print("")
print("=" * 74)
print("=== ЧТО ЗА ПРОБЫ ===")
