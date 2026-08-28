# -*- coding: utf-8 -*-
import io, json, sqlite3
ids = []
for с in io.open(r"C:\sender\_ops\v-avtootpravku.jsonl", encoding="utf-8"):
    d = json.loads(с)
    if "review" in d:
        ids.append(int(d["review"]))
c = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\sender.db", uri=True, timeout=60)
c.row_factory = sqlite3.Row
зн = ",".join("?" * len(ids))
print("переведено карточек: %d" % len(ids))
print("статусы карточек: %s" % dict(c.execute(
    "SELECT status, COUNT(*) FROM confirm_reviews WHERE id IN (%s) GROUP BY 1" % зн,
    ids).fetchall()))
print("статусы писем:    %s" % dict(c.execute(
    "SELECT m.status, COUNT(*) FROM messages m JOIN confirm_reviews cr "
    "  ON cr.message_id=m.id WHERE cr.id IN (%s) GROUP BY 1" % зн, ids).fetchall()))
print("")
print("=== расписание ===")
for r in c.execute(
        "SELECT cr.email, m.status, m.scheduled_at, m.sent_at, r.tz "
        "  FROM confirm_reviews cr JOIN messages m ON m.id=cr.message_id "
        "  LEFT JOIN recipients r ON r.id=cr.recipient_id "
        " WHERE cr.id IN (%s) ORDER BY m.scheduled_at LIMIT 8" % зн, ids):
    print("   %-30s %-10s на %s  ушло:%s  tz=%s"
          % (str(r["email"])[:30], r["status"], str(r["scheduled_at"])[:16],
             str(r["sent_at"] or "-")[:16], str(r["tz"] or "-")[:18]))
c.close()
