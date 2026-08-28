# -*- coding: utf-8 -*-
"""Что валится в журнал прямо сейчас: свежая почта или доскрёб старой."""
import json
import sqlite3
import time
from collections import Counter
from email.utils import parsedate_to_datetime
БАЗА = r"C:\sender\sender.db"
c = sqlite3.connect("file:%s?mode=ro" % БАЗА, uri=True, timeout=60)
c.row_factory = sqlite3.Row
порог = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(time.time() - 5400))
print("смотрим события, записанные после %s (последние 1.5 часа)" % порог)
по_дате, по_типу = Counter(), Counter()
строки = []
for r in c.execute(
        "SELECT id, event_type, event_ts, dedup_key, detail_json FROM events "
        " WHERE event_type IN ('reply','reply_auto','bounce','complaint') "
        "   AND id > (SELECT MAX(id)-400 FROM events) ORDER BY id"):
    if str(r["event_ts"]) < порог:
        continue
    try:
        d = json.loads(r["detail_json"] or "{}")
    except Exception:
        d = {}
    дата = str((d.get("headers") or {}).get("Date") or "")
    д = "—"
    if дата:
        try:
            t = parsedate_to_datetime(дата)
            д = t.strftime("%Y-%m-%d")
        except Exception:
            д = "не разобрал"
    по_дате[д] += 1
    по_типу[r["event_type"]] += 1
    строки.append((r["id"], r["event_type"], str(r["event_ts"])[11:19],
                   д, str(r["dedup_key"])[:34]))
print("новых входящих за 1.5 часа: %d" % len(строки))
print("  по типам: %s" % dict(по_типу))
print("  по НАСТОЯЩЕЙ дате письма: %s" % dict(sorted(по_дате.items())))
print()
for s in строки[:40]:
    print("  ev=%-7s %-10s записано %s  письмо от %s  ключ=%s" % s)
c.close()
