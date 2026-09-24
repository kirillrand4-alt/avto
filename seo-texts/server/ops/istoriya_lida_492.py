# -*- coding: utf-8 -*-
"""Кто и когда менял карточку лида: события карточки + что видно в ленте."""
import sys
sys.path.insert(0, r"C:\sender")
from sender.store import Store                                  # noqa: E402

ЛИД = int(sys.argv[1]) if len(sys.argv) > 1 else 492
store = Store(r"C:\sender\sender.db")
with store._lock:
    c = store._conn
    кол = [x[1] for x in c.execute("PRAGMA table_info(lead_events)")]
    print("--- события карточки %d ---" % ЛИД)
    print("   колонки: %s" % ", ".join(кол))
    for р in c.execute("SELECT * FROM lead_events WHERE lead_id=? ORDER BY id",
                       (ЛИД,)):
        куски = []
        for k in кол:
            if k in ("lead_id",) or р[k] in (None, ""):
                continue
            куски.append("%s=%s" % (k, str(р[k])[:60]))
        print("   " + "; ".join(куски))

    print("")
    print("--- сколько карточек в каком статусе ---")
    for р in c.execute("SELECT status, COUNT(*) n FROM leads GROUP BY 1 "
                       " ORDER BY 2 DESC"):
        print("   %-18s %5d" % (р["status"], р["n"]))

    print("")
    print("--- карточки, помеченные «не интересно», с горячим вердиктом ---")
    n = 0
    for р in c.execute(
            "SELECT id, company_name, email, reply_kind, status, updated_at "
            "  FROM leads WHERE status='not_interested' "
            "   AND reply_kind IN ('interested','question') ORDER BY id DESC "
            " LIMIT 20"):
        n += 1
        print("   лид %-5s %-28s %-12s обновлён %s"
              % (р["id"], str(р["company_name"])[:28], р["reply_kind"],
                 str(р["updated_at"])[:16]))
    print("   всего таких (первые 20 показаны): %d" % n)
print("")
print("=" * 74)
print("=== ИСТОРИЯ КАРТОЧКИ %d ===" % ЛИД)
