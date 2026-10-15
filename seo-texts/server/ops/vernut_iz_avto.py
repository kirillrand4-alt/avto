# -*- coding: utf-8 -*-
"""Вернуть в «Подтвердить отправку» карточки, переведённые кнопкой «В автоотправку»
(reason=bulk-to-auto) за последние N часов, чьи письма ещё НЕ отправлены.
Карточка → pending, письмо scheduled → pending_review. Без --katit — только счёт."""
import sqlite3, sys
from datetime import datetime, timedelta
ч = float(sys.argv[1]) if len(sys.argv) > 1 else 2
катить = "--katit" in sys.argv
от = (datetime.utcnow() - timedelta(hours=ч)).strftime("%Y-%m-%dT%H:%M:%S")
c = sqlite3.connect(r"C:\sender\sender.db", timeout=60)
кол = [r[1] for r in c.execute("PRAGMA table_info(confirm_reviews)")]
print("колонки:", кол)
вр = "decided_at" if "decided_at" in кол else "updated_at"
rows = c.execute(
    "SELECT cr.id, cr.message_id, m.status, ca.name FROM confirm_reviews cr "
    "JOIN messages m ON m.id=cr.message_id LEFT JOIN campaigns ca ON ca.id=m.campaign_id "
    "WHERE cr.status='approved' AND cr.%s>=? AND COALESCE(cr.decision_reason, cr.reason, '') LIKE '%%bulk-to-auto%%'"
    % вр if "decision_reason" in кол and "reason" in кол else
    "SELECT cr.id, cr.message_id, m.status, ca.name FROM confirm_reviews cr "
    "JOIN messages m ON m.id=cr.message_id LEFT JOIN campaigns ca ON ca.id=m.campaign_id "
    "WHERE cr.status='approved' AND cr.%s>=? AND cr.%s LIKE '%%bulk-to-auto%%'"
    % (вр, "decision_reason" if "decision_reason" in кол else "reason"), (от,)).fetchall()
from collections import Counter
print(Counter((r[2], r[3]) for r in rows))
вернуть = [r for r in rows if r[2] == "scheduled" and "Meyer" in str(r[3] or "")]
print("к возврату (ещё не ушли):", len(вернуть))
if катить and вернуть:
    теперь = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.%f")
    with c:
        for rid, mid, _s, _n in вернуть:
            n = c.execute("UPDATE messages SET status='pending_review', claimed_at=NULL, updated_at=? WHERE id=? AND status='scheduled'", (теперь, mid)).rowcount
            if n:
                sets = "status='pending', updated_at=?" + (", decided_by=NULL" if "decided_by" in кол else "") + (", %s=NULL" % вр if вр == "decided_at" else "")
                c.execute("UPDATE confirm_reviews SET %s WHERE id=?" % sets, (теперь, rid))
    print("возвращено. pending:", c.execute("SELECT COUNT(*) FROM confirm_reviews WHERE status='pending'").fetchone())
