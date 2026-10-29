# -*- coding: utf-8 -*-
"""Отбивки за N дней: вердикт пробы ДО отбивки по всем трём базам (addr_probe
перетёрт отбивкой — смотрим enrich.emails и obzvon email_probe, их время). Только чтение."""
import sqlite3
import sys
from collections import Counter
from datetime import datetime, timezone
N = int(sys.argv[1]) if len(sys.argv) > 1 else 7
c = sqlite3.connect(r"C:\sender\sender.db", timeout=60)
e = sqlite3.connect(r"C:\sender\enrich.db", timeout=60)
o = sqlite3.connect(r"file:C:\sender\obzvon-index.db?mode=ro", uri=True, timeout=60)
сч, прим = Counter(), []
for rid, ts in c.execute("SELECT recipient_id, event_ts FROM events WHERE event_type='bounce' AND event_ts >= datetime('now', ?)", ("-%d days" % N,)):
    em = (c.execute("SELECT lower(email) FROM recipients WHERE id=?", (rid,)).fetchone() or [""])[0]
    до = []
    for в, t in e.execute("SELECT probe_verdict, probe_ts FROM emails WHERE lower(email)=?", (em,)):
        try:
            tt = datetime.fromtimestamp(int(t), timezone.utc).isoformat() if t and str(t).isdigit() else str(t or "")
        except Exception:  # noqa: BLE001
            tt = str(t or "")
        if в and tt and tt[:19] < ts[:19]:
            до.append(("enrich", в, tt[:16]))
    try:
        for в, src, t in o.execute("SELECT verdict, source, ts FROM email_probe WHERE lower(email)=?", (em,)):
            if в and t and str(t)[:19] < ts[:19]:
                до.append(("obzvon:" + str(src or ""), в, str(t)[:16]))
    except sqlite3.Error:
        pass
    к = до[-1][1] if до else "пробы до отправки не видно"
    сч[к] += 1
    if len(прим) < 8 and not до:
        прим.append("%s %s" % (ts[:16], em))
print("отбивок за %d дн.: %d" % (N, sum(сч.values())))
for k, n in сч.most_common():
    print("  %4d  %s" % (n, k))
print("примеры без пробы:", прим)
