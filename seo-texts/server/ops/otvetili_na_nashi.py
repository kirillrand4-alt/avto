# -*- coding: utf-8 -*-
"""Ответил ли кто-нибудь на НАШИ ответы (ручные и через панель)."""
import json
import sqlite3

c = sqlite3.connect(r"C:\sender\sender.db", timeout=30)
c.row_factory = sqlite3.Row

виды = [r[0] for r in c.execute(
    "SELECT DISTINCT event_type FROM events ORDER BY 1")]
print("виды событий: %s" % ", ".join(виды))

наши = c.execute(
    "SELECT recipient_id, MAX(event_ts) AS когда, COUNT(*) AS n FROM events "
    " WHERE event_type IN ('reply_sent','manual_reply','reply_out','sent_reply') "
    "   AND recipient_id IS NOT NULL GROUP BY recipient_id").fetchall()
print("получателей, кому мы ответили: %d" % len(наши))

ответили = 0
for н in наши:
    поздн = c.execute(
        "SELECT event_ts, event_type, detail_json FROM events "
        " WHERE recipient_id=? AND event_type IN ('reply','reply_auto') "
        "   AND event_ts > ? ORDER BY event_ts", (н["recipient_id"], н["когда"])
    ).fetchall()
    рек = c.execute("SELECT company_name, email FROM recipients WHERE id=?",
                    (н["recipient_id"],)).fetchone()
    имя = (рек["company_name"] if рек else "?") or "?"
    if not поздн:
        print("   — %-34s %s: тишина после нашего ответа %s"
              % (имя[:34], (рек["email"] if рек else "")[:28], str(н["когда"])[:16]))
        continue
    ответили += 1
    for п in поздн:
        d = json.loads(п["detail_json"] or "{}")
        т = " ".join(str(d.get("snippet") or "").split())
        print("   ОТВЕТИЛИ %-30s %s [%s] %s"
              % (имя[:30], str(п["event_ts"])[:16], п["event_type"], т[:110]))
print("")
print("ответили на наш ответ: %d из %d" % (ответили, len(наши)))
c.close()
