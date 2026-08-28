# -*- coding: utf-8 -*-
import sqlite3
c = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\sender.db", uri=True, timeout=60)
c.row_factory = sqlite3.Row
print("=== карточки получателей группы peregen2: дата создания × статус ===")
for r in c.execute(
        "SELECT substr(cr.created_at,1,10) д, cr.status, COUNT(*) n "
        "  FROM confirm_reviews cr JOIN recipients r ON r.id=cr.recipient_id "
        " WHERE r.extra_json LIKE '%peregen2%' GROUP BY 1,2 ORDER BY 1,2"):
    print("   %s  %-10s %4d" % (r["д"], r["status"], r["n"]))
print("")
print("=== сколько получателей группы имеют ЖИВУЮ карточку ===")
r = c.execute(
    "SELECT COUNT(DISTINCT r.id) FROM recipients r "
    " WHERE r.extra_json LIKE '%peregen2%'").fetchone()[0]
ж = c.execute(
    "SELECT COUNT(DISTINCT r.id) FROM recipients r "
    "  JOIN confirm_reviews cr ON cr.recipient_id=r.id "
    " WHERE r.extra_json LIKE '%peregen2%' "
    "   AND cr.status IN ('pending','approved','sent')").fetchone()[0]
print("   в группе %d, с живой карточкой %d, без неё %d" % (r, ж, r - ж))
print("")
print("=== ключи дедупа: у скольких получателей больше одной карточки ===")
for x in c.execute(
        "SELECT cnt, COUNT(*) n FROM (SELECT cr.recipient_id, COUNT(*) cnt "
        "  FROM confirm_reviews cr JOIN recipients r ON r.id=cr.recipient_id "
        " WHERE r.extra_json LIKE '%peregen2%' GROUP BY 1) GROUP BY 1"):
    print("   карточек %d -> получателей %d" % (x["cnt"], x["n"]))
c.close()
