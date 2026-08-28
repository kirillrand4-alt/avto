# -*- coding: utf-8 -*-
"""Ответили ли клиенты на НАШИ ответы в тредах."""
import json
import sqlite3

c = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\sender.db", uri=True, timeout=60)
c.row_factory = sqlite3.Row
наши = c.execute(
    "SELECT cr.id, cr.email, cr.recipient_id, cr.decided_at, cr.subject, "
    "       cr.thread_id, r.company_name "
    "  FROM confirm_reviews cr LEFT JOIN recipients r ON r.id=cr.recipient_id "
    " WHERE cr.kind='reply' AND cr.status='sent' "
    " ORDER BY cr.decided_at").fetchall()
print("наших ответов отправлено: %d" % len(наши))
print("")
ответили = 0
for r in наши:
    когда = str(r["decided_at"] or "")
    п = []
    if r["recipient_id"]:
        for x in c.execute(
                "SELECT id, event_type, event_ts, detail_json FROM events "
                " WHERE recipient_id=? AND event_ts > ? "
                "   AND event_type IN ('reply','reply_auto','other','bounce') "
                " ORDER BY event_ts", (r["recipient_id"], когда)):
            фраза = ""
            try:
                фраза = str((json.loads(x["detail_json"] or "{}")
                             or {}).get("snippet") or "")[:110]
            except Exception:                                    # noqa: BLE001
                pass
            п.append((x["id"], x["event_type"], str(x["event_ts"])[:16], фраза))
    метка = "ОТВЕТИЛИ" if п else "тишина"
    if п:
        ответили += 1
    print("%-9s %-26s %-30s наш ответ %s"
          % (метка, str(r["email"])[:26], str(r["company_name"] or "")[:30], когда[:16]))
    print("           тема: %s" % str(r["subject"])[:70])
    for i, t, ts, ф in п:
        print("           -> #%-7s %-11s %s  %s" % (i, t, ts, ф))
print("")
print("итого: ответили %d из %d" % (ответили, len(наши)))
c.close()
