# -*- coding: utf-8 -*-
"""Работает ли новый код в живой службе: даты событий и заслон по Message-ID."""
import json
import sqlite3
import time
from collections import Counter
from email.utils import parsedate_to_datetime
БАЗА = r"C:\sender\sender.db"
ПОСЛЕ = "2026-08-28T19:05"          # момент перезапуска (UTC-время журнала ниже)
c = sqlite3.connect("file:%s?mode=ro" % БАЗА, uri=True, timeout=60)
c.row_factory = sqlite3.Row
порог = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(time.time() - 1800))
строки = list(c.execute(
    "SELECT id, event_type, event_ts, created_at, rfc_msgid, detail_json "
    "  FROM events WHERE event_type IN ('reply','reply_auto','bounce','complaint') "
    "   AND created_at >= ? ORDER BY id", (порог,)))
print("входящих событий заведено за последние 30 минут: %d" % len(строки))
совпало = разошлось = без_даты = 0
по_дням = Counter()
for r in строки:
    try:
        d = json.loads(r["detail_json"] or "{}")
    except Exception:
        d = {}
    дата = str((d.get("headers") or {}).get("Date") or "")
    по_дням[str(r["event_ts"])[:10]] += 1
    if not дата:
        без_даты += 1
        continue
    try:
        t = parsedate_to_datetime(дата)
    except Exception:
        без_даты += 1
        continue
    свой = t.astimezone().strftime("%Y-%m-%d")
    if str(r["event_ts"])[:10] == t.utctimetuple() and False:
        pass
    import datetime as _dt
    в_utc = t.astimezone(_dt.timezone.utc).strftime("%Y-%m-%d")
    if str(r["event_ts"])[:10] == в_utc:
        совпало += 1
    else:
        разошлось += 1
        print("   РАСХОЖДЕНИЕ ev=%s: событие %s, письмо %s (%s)"
              % (r["id"], str(r["event_ts"])[:16], в_utc, свой))
print("  дата события = дате письма: %d, разошлось: %d, без даты: %d"
      % (совпало, разошлось, без_даты))
print("  разложились по дням: %s" % dict(sorted(по_дням.items())))
n = c.execute("SELECT COUNT(*) FROM events WHERE rfc_msgid IS NOT NULL "
              "  AND created_at >= ?", (порог,)).fetchone()[0]
print("  из них с проставленным Message-ID: %d" % n)
дубли = c.execute(
    "SELECT COUNT(*) FROM (SELECT mailbox_id, rfc_msgid FROM events "
    "  WHERE rfc_msgid IS NOT NULL GROUP BY 1,2 HAVING COUNT(*)>1)").fetchone()[0]
print("\nгрупп-повторов по Message-ID во всём журнале: %d" % дубли)
print("\n=== динамика 7 дней ===")
for i in range(6, -1, -1):
    д = time.strftime("%Y-%m-%d", time.gmtime(time.time() - i * 86400))
    зн = {t_: c.execute("SELECT COUNT(*) FROM events WHERE event_type=? "
                        "  AND event_ts LIKE ?", (t_, д + "%")).fetchone()[0]
          for t_ in ("sent", "bounce", "reply")}
    br = (100.0 * зн["bounce"] / зн["sent"]) if зн["sent"] else 0.0
    print("  %s  отпр %5d  bounce %3d  ответы %3d  BR %.2f%%"
          % (д, зн["sent"], зн["bounce"], зн["reply"], br))
c.close()
