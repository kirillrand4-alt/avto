# -*- coding: utf-8 -*-
import io, json, sqlite3
from collections import Counter
ids = []
for с in io.open(r"C:\sender\_ops\v-avtootpravku.jsonl", encoding="utf-8"):
    d = json.loads(с)
    if "review" in d:
        ids.append(int(d["review"]))
c = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\sender.db", uri=True, timeout=60)
c.row_factory = sqlite3.Row
зн = ",".join("?" * len(ids))
print("переведено всего: %d" % len(ids))
print("карточки: %s" % dict(c.execute(
    "SELECT status, COUNT(*) FROM confirm_reviews WHERE id IN (%s) GROUP BY 1" % зн,
    ids).fetchall()))
print("письма:   %s" % dict(c.execute(
    "SELECT m.status, COUNT(*) FROM messages m JOIN confirm_reviews cr "
    "  ON cr.message_id=m.id WHERE cr.id IN (%s) GROUP BY 1" % зн, ids).fetchall()))
print("")
print("=== по дням расписания ===")
for r in c.execute(
        "SELECT substr(m.scheduled_at,1,10) д, COUNT(*) n FROM messages m "
        "  JOIN confirm_reviews cr ON cr.message_id=m.id "
        " WHERE cr.id IN (%s) AND m.status='scheduled' GROUP BY 1 ORDER BY 1" % зн,
        ids):
    print("   %s  %4d" % (r[0], r[1]))
# что осталось в очереди по первой партии
партия = []
for с in io.open(r"C:\sender\_ops\vtorye-adresa.jsonl", encoding="utf-8"):
    партия.append(int(json.loads(с)["review"]))
зн2 = ",".join("?" * len(партия))
print("")
print("=== первая партия целиком ===")
for r in c.execute("SELECT status, COUNT(*) FROM confirm_reviews "
                   " WHERE id IN (%s) GROUP BY 1 ORDER BY 2 DESC" % зн2, партия):
    print("   %-12s %5d" % (r[0], r[1]))
c.close()
