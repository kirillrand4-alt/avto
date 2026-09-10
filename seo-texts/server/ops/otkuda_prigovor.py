# -*- coding: utf-8 -*-
"""По сегодняшним отбивкам: приговор был ДО отправки или родился ИЗ отбивки."""
import sys
from collections import Counter
from datetime import datetime, timezone
sys.path.insert(0, r"C:\sender")
from sender.store import Store                                  # noqa: E402


def разбор(т):
    т = str(т or "").strip().replace("T", " ").split("+")[0].split(".")[0]
    for ф in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(т, ф).replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    return None


store = Store(r"C:\sender\sender.db")
with store._lock:
    кол = [c[1] for c in store._conn.execute("PRAGMA table_info(events)")]
    вр = next((c for c in ("ts", "created_at") if c in кол), None)
    тп = next((c for c in ("type", "event_type") if c in кол), None)
    мид = next((c for c in ("message_id", "msg_id") if c in кол), None)
    пробы = {str(r["email"] or "").lower():
             (str(r["verdict"] or ""), разбор(r["ts"]), str(r["source"] or ""))
             for r in store._conn.execute(
                 "SELECT email, verdict, ts, source FROM addr_probe")}
    письма = {int(r["id"]): (str(r["email"] or "").lower(), разбор(r["sent_at"]))
              for r in store._conn.execute(
                  "SELECT m.id, m.sent_at, r.email FROM messages m "
                  "  LEFT JOIN recipients r ON m.recipient_id = r.id "
                  " WHERE m.sent_at >= datetime('now','-2 days')")}
    отб = [int(r["m"] or 0) for r in store._conn.execute(
        "SELECT %s m FROM events WHERE %s='bounce' AND %s >= "
        "datetime('now','-2 days')" % (мид, тп, вр))]

счёт = Counter()
дыры = []
for mid in отб:
    а, s = письма.get(mid, ("", None))
    п = пробы.get(а)
    if not п:
        счёт["вердикта нет вовсе"] += 1
        continue
    вердикт, ts, ист = п
    if ист and ист != "проба":
        счёт["приговор ИЗ ОТБИВКИ (source=%s)" % ист] += 1
    elif ts and s and ts <= s:
        счёт["ПРОБА ЗНАЛА ДО ОТПРАВКИ"] += 1
        дыры.append((а, вердикт, ист, ts, s))
    else:
        счёт["проба узнала после отправки"] += 1
for а, в, ист, ts, s in дыры[:15]:
    print("   ДЫРА: %-34s %-10s src=%-12s приговор %s → отправка %s"
          % (а[:34], в, ист, ts.strftime("%m-%d %H:%M"), s.strftime("%m-%d %H:%M")))
print("")
print("=" * 74)
print("=== ОТКУДА ПРИГОВОР У ОТБИТЫХ (2 дня) ===")
print("отбивок разобрано: %d" % len(отб))
for к, в in счёт.most_common():
    print("   %-44s %4d" % (к, в))
