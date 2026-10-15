# -*- coding: utf-8 -*-
"""Кто перевёл письма Meyer в scheduled за последние N часов: журналы БД и логи панели. Только чтение."""
import glob, io, os, sqlite3, sys
from datetime import datetime, timedelta
ч = float(sys.argv[1]) if len(sys.argv) > 1 else 1
от = (datetime.utcnow() - timedelta(hours=ч)).strftime("%Y-%m-%dT%H:%M:%S")
c = sqlite3.connect(r"C:\sender\sender.db", timeout=60)
print("updated_at первых/последних:", c.execute("SELECT MIN(updated_at), MAX(updated_at), MIN(scheduled_at), MAX(scheduled_at), COUNT(*) FROM messages WHERE status='scheduled' AND campaign_id IN (SELECT id FROM campaigns WHERE name LIKE '%Meyer%') AND updated_at>=?", (от,)).fetchone())
for (t,) in c.execute("SELECT name FROM sqlite_master WHERE type='table'"):
    кол = [r[1] for r in c.execute("PRAGMA table_info(%s)" % t)]
    вр = next((k for k in ("ts", "created_at", "at", "time") if k in кол), None)
    if not вр or not any(w in t for w in ("event", "audit", "log", "action", "history", "journal")):
        continue
    try:
        rows = c.execute("SELECT * FROM %s WHERE %s>=? ORDER BY %s DESC LIMIT 400" % (t, вр, вр), (от,)).fetchall()
    except Exception as ex:
        print(t, ex); continue
    print("== %s (%d), колонки %s" % (t, len(rows), кол))
    from collections import Counter
    сч = Counter(str([v for k, v in zip(кол, r) if k not in (вр, "id", "message_id", "recipient_id")])[:160] for r in rows)
    for k, v in сч.most_common(12): print("  %4d %s" % (v, k))
for ф in sorted(glob.glob(r"C:\sender\logs\*.log") + glob.glob(r"C:\sender\*.log"), key=os.path.getmtime)[-4:]:
    т = io.open(ф, encoding="utf-8", errors="replace").read()[-200000:].splitlines()
    хит = [s for s in т if any(w in s.lower() for w in ("approve", "avto", "auto_send", "schedul", "автоотправ"))]
    print("== лог", ф, len(хит)); print("\n".join(х[:220] for х in хит[-15:]))
