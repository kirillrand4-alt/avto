# -*- coding: utf-8 -*-
"""Вернуть письма белорусской партии из отправки в очередь подтверждений.

Владелец 26.08: «белорусов верни в очередь подтверждений из отправки, там
перепишем заголовки». Возвращаем только то, что ЕЩЁ НЕ УШЛО: отправленное
письмо вернуть нельзя, и делать вид, что можно, — врать.

    python belorusy_v_ochered.py            # показать, что где
    python belorusy_v_ochered.py primenit   # вернуть в pending
"""
import json
import sqlite3
import sys
import time
from collections import Counter

ДЕЛАТЬ = "primenit" in sys.argv[1:]
ГРУППА = "prodexpo2025"

c = sqlite3.connect(r"C:\sender\sender.db", timeout=30)
c.row_factory = sqlite3.Row

# получатели группы
свои = []
for r in c.execute("SELECT id, email, company_name, COALESCE(extra_json,'') e "
                   "FROM recipients WHERE source='prodexpo-2025'"):
    гр = []
    try:
        гр = (json.loads(r["e"]) or {}).get("gruppy") or []
    except Exception:                                         # noqa: BLE001
        pass
    if ГРУППА in гр:
        свои.append(r["id"])
print("получателей группы %s: %d" % (ГРУППА, len(свои)))
if not свои:
    raise SystemExit(0)

места = ",".join("?" * len(свои))
карточки = c.execute(
    "SELECT cr.id, cr.status, cr.message_id, cr.created_at, "
    "       substr(cr.subject,1,60) s, m.status mst "
    "  FROM confirm_reviews cr LEFT JOIN messages m ON m.id=cr.message_id "
    " WHERE cr.recipient_id IN (%s) ORDER BY cr.id" % места, свои).fetchall()
свод = Counter((к["status"], к["mst"]) for к in карточки)
print("карточек: %d" % len(карточки))
for (ст, мст), n in свод.most_common():
    print("   карточка=%-10s письмо=%-14s %d" % (ст, мст, n))

вернуть = [к for к in карточки if к["status"] in ("approved", "edited")
           and (к["mst"] or "") not in ("sent", "sending")]
ушли = [к for к in карточки if к["status"] == "sent"
        or (к["mst"] or "") in ("sent", "sending")]
print("")
print("к возврату: %d | уже ушло (вернуть нельзя): %d" % (len(вернуть), len(ушли)))
for к in вернуть[:8]:
    print("   #%-6s %-10s %s" % (к["id"], к["status"], к["s"]))
if ушли:
    print("   УШЛИ:")
    for к in ушли[:8]:
        print("   #%-6s %-10s %-10s %s" % (к["id"], к["status"], к["mst"], к["s"]))

if not ДЕЛАТЬ:
    print("\nвхолостую. Вернуть — primenit")
    raise SystemExit(0)

сейчас = time.strftime("%Y-%m-%dT%H:%M:%S")
возвращено = 0
for к in вернуть:
    c.execute("UPDATE confirm_reviews SET status='pending', decided_at=NULL, "
              "decided_by=NULL, updated_at=? WHERE id=? AND status IN "
              "('approved','edited')", (сейчас, к["id"]))
    if к["message_id"]:
        c.execute("UPDATE messages SET status='pending_review', updated_at=? "
                  " WHERE id=? AND status IN ('scheduled','queued','pending_review')",
                  (сейчас, к["message_id"]))
    возвращено += 1
c.commit()
print("\nвозвращено в очередь: %d" % возвращено)
