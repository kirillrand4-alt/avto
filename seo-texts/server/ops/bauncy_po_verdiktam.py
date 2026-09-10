# -*- coding: utf-8 -*-
"""Отбивки в разрезе вердикта пробы: правда ли виноваты «принимает всё»."""
import sys
from collections import Counter
sys.path.insert(0, r"C:\sender")
from sender.store import Store                                  # noqa: E402

store = Store(r"C:\sender\sender.db")
with store._lock:
    кол = [c[1] for c in store._conn.execute("PRAGMA table_info(events)")]
    вр = next((c for c in ("ts", "created_at") if c in кол), None)
    тп = next((c for c in ("type", "event_type") if c in кол), None)
    мид = next((c for c in ("message_id", "msg_id") if c in кол), None)
    пробы = {str(r["email"] or "").lower(): str(r["verdict"] or "")
             for r in store._conn.execute("SELECT email, verdict FROM addr_probe")}
    адрес_письма = {int(r["id"]): str(r["email"] or "").lower()
                    for r in store._conn.execute(
                        "SELECT m.id, r.email FROM messages m "
                        "  LEFT JOIN recipients r ON m.recipient_id = r.id "
                        " WHERE m.updated_at >= datetime('now','-4 days')")}

    def свод(вырез, метка):
        ушло = Counter()
        for r in store._conn.execute(
                "SELECT m.id FROM messages m WHERE m.status='sent' "
                "  AND m.sent_at >= datetime('now',?)", (вырез,)):
            а = адрес_письма.get(int(r["id"]), "")
            ушло[пробы.get(а) or "без вердикта"] += 1
        отб = Counter()
        for r in store._conn.execute(
                "SELECT %s m FROM events WHERE %s='bounce' AND %s >= "
                "datetime('now',?)" % (мид, тп, вр), (вырез,)):
            а = адрес_письма.get(int(r["m"] or 0), "")
            отб[пробы.get(а) or "без вердикта"] += 1
        print("")
        print("--- %s ---" % метка)
        print("   %-18s %7s %8s %8s" % ("вердикт пробы", "ушло", "отбивок", "доля"))
        for к in sorted(set(list(ушло) + list(отб)), key=lambda x: -ушло.get(x, 0)):
            у, б = ушло.get(к, 0), отб.get(к, 0)
            print("   %-18s %7d %8d %7.1f%%"
                  % (к, у, б, (100.0 * б / у) if у else 0))
        print("   %-18s %7d %8d %7.1f%%"
              % ("ИТОГО", sum(ушло.values()), sum(отб.values()),
                 100.0 * sum(отб.values()) / max(1, sum(ушло.values()))))

    свод("start of day", "сегодня")
    свод("-1 day", "за сутки")
    свод("-4 days", "за четыре дня")

    # что стоит в очереди сейчас, по вердиктам
    import importlib, sys as s2
    s2.path.insert(0, r"C:\sender\server\ops")
    V = importlib.import_module("varianty_pisma")
    оч = Counter()
    for r in store._conn.execute(
            "SELECT status, email FROM confirm_reviews WHERE subject IN (%s) "
            "  AND status IN ('pending','approved')"
            % ",".join("?" * len(V.ТЕМЫ)), tuple(V.ТЕМЫ)):
        оч[пробы.get(str(r["email"] or "").lower()) or "без вердикта"] += 1
print("")
print("=" * 70)
print("=== ЧТО ЖДЁТ В ОЧЕРЕДИ ===")
for к, в in оч.most_common():
    print("   %-18s %6d" % (к, в))
