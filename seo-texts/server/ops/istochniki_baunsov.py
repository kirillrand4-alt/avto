# -*- coding: utf-8 -*-
"""Откуда сегодняшние баунсы: копии на второй адрес или обычная генерация."""
import io
import json
import sqlite3
from collections import Counter

наши = set()
for ф in (r"C:\sender\_ops\vtorye-adresa.jsonl", r"C:\sender\_ops\vtorye-adresa-2.jsonl"):
    try:
        for с in io.open(ф, encoding="utf-8"):
            d = json.loads(с)
            if "email" in d:
                наши.add(d["email"].lower())
    except FileNotFoundError:
        pass
c = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\sender.db", uri=True, timeout=60)
c.row_factory = sqlite3.Row
послано = c.execute(
    "SELECT LOWER(rc.email) email, rc.mx_provider, rc.source, m.mailbox_id "
    "  FROM messages m JOIN recipients rc ON rc.id=m.recipient_id "
    " WHERE m.status='sent' AND substr(m.sent_at,1,10)=date('now')").fetchall()
отбились = {}
for r in c.execute(
        "SELECT LOWER(rc.email) email, e.detail_json FROM events e "
        "  JOIN recipients rc ON rc.id=e.recipient_id "
        " WHERE e.event_type='bounce' AND substr(e.event_ts,1,10)=date('now')"):
    отбились[r["email"]] = str(r["detail_json"] or "")
c.close()
print("отправлено сегодня: %d, отбилось: %d (%.2f%%)"
      % (len(послано), len(отбились), 100.0 * len(отбились) / max(1, len(послано))))

группы = Counter()
отб_гр = Counter()
for r in послано:
    г = "копия на второй адрес" if r["email"] in наши else "обычная генерация"
    группы[г] += 1
    if r["email"] in отбились:
        отб_гр[г] += 1
print("")
print("=== по источнику ===")
for г in группы:
    n, o = группы[г], отб_гр.get(г, 0)
    print("   %-24s отправлено %4d, отбилось %3d  (%.2f%%)"
          % (г, n, o, 100.0 * o / max(1, n)))

пров = Counter()
отб_пров = Counter()
for r in послано:
    п = str(r["mx_provider"] or "?")
    пров[п] += 1
    if r["email"] in отбились:
        отб_пров[п] += 1
print("")
print("=== по почтовику ===")
for п, n in пров.most_common(6):
    o = отб_пров.get(п, 0)
    print("   %-12s отправлено %4d, отбилось %3d  (%.2f%%)"
          % (п, n, o, 100.0 * o / max(1, n)))

print("")
print("=== причины ===")
for а, д in отбились.items():
    к = "?"
    try:
        j = json.loads(д or "{}")
        dsn = j.get("dsn") or {}
        к = "%s %s" % (dsn.get("smtp_code"), str(dsn.get("diagnostic") or "")[:60])
    except Exception:                                            # noqa: BLE001
        pass
    print("   %-34s %s %s" % (а[:34], "[копия]" if а in наши else "[обычн]", к))
