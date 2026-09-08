# -*- coding: utf-8 -*-
"""Сколько писем в очереди уже проверено пробой и успеет ли она к завтра."""
import sys
from collections import Counter
from datetime import datetime, timezone
sys.path.insert(0, r"C:\sender")
from sender.store import Store                                  # noqa: E402
sys.path.insert(0, r"C:\sender\server\ops")
import varianty_pisma as V                                      # noqa: E402


def разбор(т):
    т = str(т or "").strip().replace("T", " ").split("+")[0].split(".")[0]
    for ф in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(т, ф).replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    return None


store = Store(r"C:\sender\sender.db")
теперь = datetime.now(timezone.utc)
with store._lock:
    пробы = {str(р["email"] or "").lower(): str(р["verdict"] or "")
             for р in store._conn.execute("SELECT email, verdict FROM addr_probe")}
    очередь = store._conn.execute(
        "SELECT status, email FROM confirm_reviews WHERE subject IN (%s) "
        "  AND status IN ('pending','approved')"
        % ",".join("?" * len(V.ТЕМЫ)), tuple(V.ТЕМЫ)).fetchall()
    # темп работника проб за сутки
    темп = Counter()
    for р in store._conn.execute(
            "SELECT ts FROM addr_probe WHERE ts >= datetime('now','-1 day')"):
        d = разбор(р["ts"])
        if d:
            темп[d.strftime("%Y-%m-%d %H")] += 1

с = Counter()
for р in очередь:
    в = пробы.get(str(р["email"] or "").lower())
    с["не проверен" if в is None else в] += 1

всего = len(очередь)
непроверенных = с.get("не проверен", 0)
проверено = всего - непроверенных
мёртвых = с.get("нет ящика", 0) + с.get("нет MX", 0)
доля_мёртвых = (100.0 * мёртвых / проверено) if проверено else 0
часы = sorted(темп)
за_сутки = sum(темп.values())
в_час = (за_сутки / max(1, len(часы))) if часы else 0

print("--- вердикты по очереди партии ---")
for к, в in с.most_common():
    print("   %-22s %5d  (%.1f%%)" % (к, в, 100.0 * в / всего if всего else 0))
print("")
print("--- темп работника проб (последние часы) ---")
for ч in часы[-8:]:
    print("   %s  %4d" % (ч, темп[ч]))
print("")
print("=" * 74)
print("=== ПРОБЫ ПО ОЧЕРЕДИ ===")
print("писем в очереди: %d; проверено: %d (%.0f%%); не проверено: %d"
      % (всего, проверено, 100.0 * проверено / всего if всего else 0,
         непроверенных))
print("среди проверенных мёртвых: %d (%.1f%%)" % (мёртвых, доля_мёртвых))
print("ожидаемо мёртвых среди непроверенных: около %d"
      % int(непроверенных * доля_мёртвых / 100.0))
print("проб за сутки: %d, в среднем %.0f в час" % (за_сутки, в_час))
if в_час:
    print("на непроверенные уйдёт около %.1f часов" % (непроверенных / в_час))
