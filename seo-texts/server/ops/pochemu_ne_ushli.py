# -*- coding: utf-8 -*-
"""Почему письма не ушли: на какие даты стоят сроки и что мешает."""
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
sys.path.insert(0, r"C:\sender")
sys.path.insert(0, r"C:\sender\server\ops")
from sender.auto_send import window_from                        # noqa: E402
from sender.config import Config                                # noqa: E402
from sender.store import Store                                  # noqa: E402
import varianty_pisma as V                                      # noqa: E402


def разбор(т):
    т = str(т or "").strip().replace("T", " ").split("+")[0].split(".")[0]
    for ф in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(т, ф).replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    return None


cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
теперь = datetime.now(timezone.utc)
окно = window_from(store, cfg)
print("сейчас UTC %s (Москва %s); окно %s-%s по зоне получателя"
      % (теперь.strftime("%m-%d %H:%M"),
         (теперь + timedelta(hours=3)).strftime("%H:%M"),
         окно.get("start"), окно.get("end")))

with store._lock:
    по_дням = Counter()
    статусы = Counter()
    for р in store._conn.execute(
            """SELECT m.status, m.scheduled_at FROM confirm_reviews c
                 JOIN messages m ON c.message_id = m.id
                WHERE c.subject IN (%s)""" % ",".join("?" * len(V.ТЕМЫ)),
            tuple(V.ТЕМЫ)):
        статусы[str(р["status"])] += 1
        if str(р["status"]) == "scheduled":
            d = разбор(р["scheduled_at"])
            по_дням[d.strftime("%Y-%m-%d %H") if d else "срок не задан"] += 1
    ушло = Counter()
    for р in store._conn.execute(
            "SELECT sent_at FROM messages WHERE status='sent' AND sent_at >= "
            "datetime('now','-4 days')"):
        ушло[str(р["sent_at"])[:10]] += 1

print("")
print("--- письма партии по статусам ---")
for к, в in статусы.most_common():
    print("   %-18s %6d" % (к, в))
print("")
print("--- на какие часы стоят сроки (топ-12) ---")
for к in sorted(по_дням)[:12]:
    print("   %s  %5d" % (к, по_дням[к]))
print("")
print("--- реально отправлено по дням ---")
for к in sorted(ушло):
    print("   %s  %5d" % (к, ушло[к]))
print("")
print("=" * 74)
print("=== ПОЧЕМУ НЕ УШЛИ ===")
созрели = sum(в for к, в in по_дням.items()
              if к != "срок не задан" and к <= теперь.strftime("%Y-%m-%d %H"))
print("со сроком в прошлом (созрели): %d" % созрели)
print("со сроком в будущем: %d"
      % (sum(по_дням.values()) - созрели - по_дням.get("срок не задан", 0)))
