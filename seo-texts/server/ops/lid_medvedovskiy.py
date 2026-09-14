# -*- coding: utf-8 -*-
"""Был ли ответ Медведовского ЗПП заведён лидом и в каком он состоянии."""
import sys
from collections import Counter
sys.path.insert(0, r"C:\sender")
from sender.store import Store                                  # noqa: E402

ПОЧТА = "krimck1600@mail.ru"
store = Store(r"C:\sender\sender.db")
with store._lock:
    кол = [c[1] for c in store._conn.execute("PRAGMA table_info(leads)")]
    строки = store._conn.execute(
        "SELECT * FROM leads WHERE email=? OR company_name LIKE ?",
        (ПОЧТА, "%едведовск%")).fetchall()
    print("лидов найдено: %d" % len(строки))
    for р in строки:
        print("")
        print("=" * 74)
        for k in кол:
            з = р[k]
            if з in (None, ""):
                continue
            s = str(з)
            if len(s) > 90:
                print("   --- %s ---" % k)
                print(s[:1200])
            else:
                print("   %-16s %s" % (k, s))
        соб = store._conn.execute(
            "SELECT action, from_status, to_status, created_at FROM lead_events "
            " WHERE lead_id=? ORDER BY id", (р["id"],)).fetchall()
        print("   --- события карточки (%d) ---" % len(соб))
        for с in соб:
            print("      %s  %-18s %s → %s"
                  % (с["created_at"], с["action"], с["from_status"], с["to_status"]))
    # письма и события по этому адресу
    print("")
    print("--- письма на этот адрес ---")
    for р in store._conn.execute(
            "SELECT m.id, m.status, m.subject, m.sent_at, m.mailbox_id "
            "  FROM messages m JOIN recipients r ON m.recipient_id = r.id "
            " WHERE r.email=? ORDER BY m.id", (ПОЧТА,)):
        print("   письмо %-7s %-12s %s  %s"
              % (р["id"], р["status"], str(р["sent_at"])[:16], str(р["subject"])[:44]))
    кол_е = [c[1] for c in store._conn.execute("PRAGMA table_info(events)")]
    тп = next((c for c in ("type", "event_type") if c in кол_е), None)
    вр = next((c for c in ("ts", "created_at") if c in кол_е), None)
    пч = next((c for c in ("email",) if c in кол_е), None)
    print("")
    print("--- события по адресу ---")
    if пч:
        for р in store._conn.execute(
                "SELECT %s t, %s k FROM events WHERE %s=? ORDER BY %s"
                % (вр, тп, пч, вр), (ПОЧТА,)):
            print("   %s  %s" % (р["t"], р["k"]))
print("")
print("=" * 74)
print("=== ЛИД МЕДВЕДОВСКОГО ЗПП ===")
