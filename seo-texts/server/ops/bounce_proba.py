# -*- coding: utf-8 -*-
"""Отбивки за N дней: была ли проба по адресу и какой вердикт (до отбивки). Только чтение.
    bounce_proba.py [дней=7]"""
import json
import sqlite3
import sys
from collections import Counter
N = int(sys.argv[1]) if len(sys.argv) > 1 else 7
c = sqlite3.connect(r"C:\sender\sender.db", timeout=60)
cols = [r[1] for r in c.execute("PRAGMA table_info(addr_probe)")]
тс = next((x for x in ("checked_at", "ts", "probed_at", "updated_at") if x in cols), None)
проба = {}
for r in c.execute("SELECT lower(email), verdict%s FROM addr_probe" % ((", " + тс) if тс else "")):
    проба[r[0]] = (r[1], r[2] if тс else "")
отправлено = Counter()
for (em,) in c.execute("SELECT lower(r.email) FROM messages m JOIN recipients r ON r.id=m.recipient_id WHERE m.status='sent' AND m.sent_at >= datetime('now', ?)", ("-%d days" % N,)):
    в = проба.get(em, ("нет пробы", ""))[0]
    отправлено[в] += 1
сч, тип, прим = Counter(), Counter(), []
for eid, rid, ts, dj in c.execute("SELECT e.id, e.recipient_id, e.event_ts, e.detail_json FROM events e WHERE e.event_type='bounce' AND e.event_ts >= datetime('now', ?)", ("-%d days" % N,)):
    em = (c.execute("SELECT lower(email) FROM recipients WHERE id=?", (rid,)).fetchone() or [""])[0]
    в, когда = проба.get(em, ("нет пробы", ""))
    д = json.loads(dj or "{}")
    жёстк = str(д.get("bounce_type") or д.get("kind") or д.get("type") or "")
    # вердикт мог поставить сам bounce (после) — смотрим время пробы
    if когда and str(когда)[:19] >= str(ts)[:19] and в in ("нет ящика", "нет MX"):
        в = "проба после отбивки (%s)" % в
    сч[в] += 1
    тип[(в, жёстк)] += 1
    if len(прим) < 12:
        прим.append("%s | %s | %s | %s" % (ts[:16], em, в, (д.get("reason") or д.get("diagnostic") or д.get("snippet") or "")[:80]))
print("отправлено за %d дн. по вердикту пробы:" % N, dict(отправлено))
print("отбивки по вердикту пробы:", dict(сч))
for в, n in сч.items():
    if отправлено.get(в.split(" (")[0]):
        pass
for в in отправлено:
    print("   доля отбивок при «%s»: %d из %d (%.1f%%)" % (в, сч.get(в, 0), отправлено[в], 100.0 * сч.get(в, 0) / max(1, отправлено[в])))
print("тип отбивки:", тип.most_common(10))
print("\n".join(прим))
