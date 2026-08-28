# -*- coding: utf-8 -*-
import json, sqlite3
from collections import Counter
c = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\sender.db", uri=True, timeout=60)
c.row_factory = sqlite3.Row
сч = Counter()
for r in c.execute("SELECT id, status, reply_kind, need FROM leads"):
    т = str(r["need"] or "").strip()
    if not т:
        сч["ПУСТАЯ потребность / %s" % r["reply_kind"]] += 1
    else:
        сч["с текстом"] += 1
for к, n in сч.most_common():
    print("   %-42s %4d" % (к, n))
print("")
пуст = 0
всего = 0
for r in c.execute("SELECT detail_json FROM events "
                   " WHERE event_type IN ('reply','reply_auto') "
                   "   AND substr(event_ts,1,10) >= '2026-08-20'"):
    всего += 1
    try:
        s = str((json.loads(r["detail_json"] or "{}") or {}).get("snippet") or "")
    except Exception:
        s = ""
    if not s.strip():
        пуст += 1
print("входящих ответов с 20.08: %d, из них с пустым телом: %d (%.0f%%)"
      % (всего, пуст, 100.0 * пуст / max(1, всего)))
c.close()
