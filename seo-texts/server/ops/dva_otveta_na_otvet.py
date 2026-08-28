# -*- coding: utf-8 -*-
import json, sqlite3
c = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\sender.db", uri=True, timeout=60)
c.row_factory = sqlite3.Row
for почта in ("mail@ufntc.ru",):
    print("=" * 66)
    print(почта)
    r = c.execute("SELECT id, inn, company_name FROM recipients WHERE email=?",
                  (почта,)).fetchone()
    if r is None:
        print("   получателя нет"); continue
    print("   rid %s | %s" % (r["id"], r["company_name"]))
    л = c.execute("SELECT id, status, reply_kind, phone, need, created_at, "
                  "       updated_at FROM leads WHERE recipient_id=? OR email=?",
                  (r["id"], почта)).fetchall()
    if not л:
        print("   ЛИДА НЕТ")
    for x in л:
        print("   лид #%s %s | тип %s | тел %s | создан %s | обновлён %s"
              % (x["id"], x["status"], x["reply_kind"], x["phone"],
                 str(x["created_at"])[:16], str(x["updated_at"])[:16]))
        print("      что написал: %s" % str(x["need"] or "")[:150])
    print("   --- события ---")
    for x in c.execute("SELECT id, event_type, event_ts, detail_json FROM events "
                       " WHERE recipient_id=? ORDER BY event_ts", (r["id"],)):
        ф = ""
        try:
            ф = str((json.loads(x["detail_json"] or "{}") or {}).get("snippet") or "")[:60]
        except Exception:
            pass
        print("      #%-7s %-11s %s %s" % (x["id"], x["event_type"],
                                           str(x["event_ts"])[:16], ф))
c.close()
