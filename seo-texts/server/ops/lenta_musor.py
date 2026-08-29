# -*- coding: utf-8 -*-
"""Что за мусор в ленте событий: разбираем три показательных события."""
import json
import sqlite3
БАЗА = r"C:\sender\sender.db"
c = sqlite3.connect("file:%s?mode=ro" % БАЗА, uri=True, timeout=60)
c.row_factory = sqlite3.Row
for eid in (308597, 308593, 308591):
    r = c.execute("SELECT id, event_type, event_ts, mailbox_id, recipient_id, "
                  "       dedup_key, detail_json FROM events WHERE id=?",
                  (eid,)).fetchone()
    if not r:
        print("ev=%s нет" % eid)
        continue
    try:
        d = json.loads(r["detail_json"] or "{}")
    except Exception:
        d = {}
    h = d.get("headers") or {}
    print("=" * 70)
    print("ev=%s тип=%s %s ящик=%s rid=%s"
          % (r["id"], r["event_type"], str(r["event_ts"])[:19], r["mailbox_id"],
             r["recipient_id"]))
    print("  ключ: %s" % r["dedup_key"])
    print("  От:   %s" % str(h.get("From") or "")[:90])
    print("  Тема: %s" % str(h.get("Subject") or "")[:90])
    print("  Content-Type: %s" % str(h.get("Content-Type") or "")[:90])
    print("  вид в detail: %s" % d.get("kind"))
    т = str(d.get("snippet") or "")
    печатных = sum(1 for x in т[:400] if x.isprintable())
    print("  длина текста %d, печатных из первых 400: %d" % (len(т), печатных))
    print("  начало: %r" % т[:180])
print("=" * 70)
print("\n=== сколько таких в ленте вообще ===")
всего = мусор = dmarc = 0
for r in c.execute("SELECT id, detail_json FROM events WHERE event_type='other'"):
    всего += 1
    try:
        d = json.loads(r["detail_json"] or "{}")
    except Exception:
        continue
    т = str(d.get("snippet") or "")
    if not т:
        continue
    if "aggregate DMARC report" in т or "report_metadata" in т.lower():
        dmarc += 1
    доля = sum(1 for x in т[:300] if x.isprintable()) / max(1, len(т[:300]))
    if доля < 0.85:
        мусор += 1
print("событий 'other': %d, из них двоичный мусор: %d, отчёты DMARC: %d"
      % (всего, мусор, dmarc))
c.close()
