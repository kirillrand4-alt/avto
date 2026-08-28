# -*- coding: utf-8 -*-
"""Из чего сложились сегодняшние 87 отбивок и 75 ответов."""
import json
import sqlite3
from collections import Counter

c = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\sender.db", uri=True, timeout=60)
c.row_factory = sqlite3.Row
ДЕНЬ = "2026-08-28"

for тип in ("bounce", "reply", "reply_auto", "complaint", "sent"):
    n = c.execute("SELECT COUNT(*) FROM events WHERE event_type=? "
                  "  AND event_ts LIKE ?", (тип, ДЕНЬ + "%")).fetchone()[0]
    print("%-12s сегодня: %d" % (тип, n))
print()

for тип in ("bounce", "reply"):
    print("=== %s: когда письмо РЕАЛЬНО пришло (Date из заголовков) ===" % тип)
    по_дате = Counter()
    по_часу = Counter()
    без_даты = 0
    for r in c.execute("SELECT id, event_ts, detail_json FROM events "
                       " WHERE event_type=? AND event_ts LIKE ?",
                       (тип, ДЕНЬ + "%")):
        try:
            d = json.loads(r["detail_json"] or "{}")
        except Exception:
            d = {}
        h = d.get("headers") or {}
        дата = str(h.get("Date") or "")
        if not дата:
            без_даты += 1
            по_дате["нет заголовка Date"] += 1
        else:
            # Rfc2822: «Fri, 28 Aug 2026 12:17:03 +0300»
            ч = дата.split(",")[-1].strip().split(" ")
            по_дате[" ".join(ч[:3]) if len(ч) >= 3 else дата[:20]] += 1
        по_часу[str(r["event_ts"])[11:13]] += 1
    for к, v in sorted(по_дате.items(), key=lambda x: -x[1])[:15]:
        print("   %-24s %d" % (к, v))
    print("   по часу записи: %s"
          % ", ".join("%s:00→%d" % (к, v) for к, v in sorted(по_часу.items())))
    print()

print("=== ответы сегодня: тема и от кого (первые 40) ===")
for r in c.execute("SELECT id, event_ts, mailbox_id, detail_json FROM events "
                   " WHERE event_type='reply' AND event_ts LIKE ? "
                   " ORDER BY event_ts", (ДЕНЬ + "%",)):
    d = {}
    try:
        d = json.loads(r["detail_json"] or "{}")
    except Exception:
        pass
    h = d.get("headers") or {}
    print("  ev=%s %s | Date: %-32s | %s"
          % (r["id"], str(r["event_ts"])[11:19], str(h.get("Date") or "—")[:32],
             str(h.get("From") or "")[:50]))
c.close()
