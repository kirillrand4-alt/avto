# -*- coding: utf-8 -*-
"""send_log и events в окне времени: send_log_okno.py ОТ ДО [подстрока]. Только чтение."""
import sqlite3, sys
c = sqlite3.connect(r"C:\sender\sender.db", timeout=90)
от, до = sys.argv[1], sys.argv[2]; п = sys.argv[3] if len(sys.argv) > 3 else ""
шк = [x[1] for x in c.execute("PRAGMA table_info(send_log)")]; print("send_log:", шк)
for r in c.execute("SELECT * FROM send_log WHERE ts BETWEEN ? AND ? ORDER BY ts", (от, до)):
    if п in str(r): print("  ", tuple(str(x)[:70] for x in r))
шк = [x[1] for x in c.execute("PRAGMA table_info(events)")]; print("events:", шк)
тс = next((x for x in шк if x in ("ts", "created_at", "at")), шк[1])
for r in c.execute("SELECT * FROM events WHERE %s BETWEEN ? AND ? ORDER BY %s" % (тс, тс), (от, до)):
    if п in str(r): print("  ", tuple(str(x)[:90] for x in r))
