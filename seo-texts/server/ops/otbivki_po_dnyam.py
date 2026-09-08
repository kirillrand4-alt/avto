# -*- coding: utf-8 -*-
"""Доля отбивок по дням: «много» это относительно чего."""
import sys
from collections import Counter
sys.path.insert(0, r"C:\sender")
from sender.store import Store                                  # noqa: E402

store = Store(r"C:\sender\sender.db")
ушло = Counter()
отб = Counter()
спам = Counter()
with store._lock:
    кол = [c[1] for c in store._conn.execute("PRAGMA table_info(events)")]
    вр = next((c for c in ("ts", "created_at") if c in кол), None)
    тп = next((c for c in ("type", "event_type") if c in кол), None)
    for р in store._conn.execute(
            "SELECT sent_at FROM messages WHERE status='sent' AND sent_at >= "
            "datetime('now','-9 days')"):
        ушло[str(р["sent_at"])[:10]] += 1
    for р in store._conn.execute(
            "SELECT %s t, %s k FROM events WHERE %s IN ('bounce','reject_spam') "
            "  AND %s >= datetime('now','-9 days')" % (вр, тп, тп, вр)):
        д = str(р["t"])[:10]
        (отб if str(р["k"]) == "bounce" else спам)[д] += 1
print("   %-12s %7s %8s %7s %8s %7s" % ("день", "ушло", "отбивок", "доля",
                                        "спам-отк", "доля"))
for д in sorted(set(list(ушло) + list(отб) + list(спам))):
    у, б, с = ушло.get(д, 0), отб.get(д, 0), спам.get(д, 0)
    print("   %-12s %7d %8d %6.1f%% %8d %6.1f%%"
          % (д, у, б, (100.0 * б / у) if у else 0, с, (100.0 * с / у) if у else 0))
print("")
print("=" * 70)
print("=== ОТБИВКИ ПО ДНЯМ ===")
print("порог гейта по отбивкам: домен 10%%, ящик 10%%")
