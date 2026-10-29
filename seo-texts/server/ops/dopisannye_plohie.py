# -*- coding: utf-8 -*-
"""Починенные письма яруса C с битым названием (ОПФ вместо имени, «коллеги из»).
    dopisannye_plohie.py [--snyat]"""
import io
import json
import re
import sqlite3
import sys
from datetime import datetime
з = [json.loads(s) for s in io.open(r"C:\sender\_ops\dopisannye-v4c.jsonl", encoding="utf-8")]
з = list({x["recipient_id"]: x for x in з if x.get("review_id")}.values())
ПЛОХО = re.compile(r"(общество с ограниченной|обществе с ограниченной|открытое акционерное|закрытое акционерное|коллеги из|"
                   r"\bООО\s*[!,.]|«ООО»|«\s*»|сельскохозяйственн\w+ производственн\w+ ко\b)", re.I)
плохие = [x for x in з if ПЛОХО.search((x.get("тема") or "") + "\n" + (x.get("тело") or "").split("\n\n")[0] + "\n" + (x.get("тело") or "")[:600])]
print("починено:", len(з), "| с битым названием:", len(плохие))
for x in плохие[:10]:
    м = ПЛОХО.search((x.get("тема") or "") + "\n" + (x.get("тело") or ""))
    print("  %s | %s | ...%s..." % (x["review_id"], x["причина"][:40], ((x.get("тема") or "") + " / " + (x.get("тело") or ""))[max(0, м.start() - 40):м.end() + 40].replace("\n", " ") if м else ""))
if "--snyat" in sys.argv:
    c = sqlite3.connect(r"C:\sender\sender.db", timeout=60)
    т = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S")
    n = 0
    with c:
        for x in плохие:
            cur = c.execute("UPDATE confirm_reviews SET status='skipped', reason='починка: битое название компании', decided_at=?, updated_at=? "
                            "WHERE id=? AND status='pending'", (т, т, x["review_id"]))
            n += cur.rowcount
            mid = c.execute("SELECT message_id FROM confirm_reviews WHERE id=?", (x["review_id"],)).fetchone()
            if mid and mid[0]:
                c.execute("UPDATE messages SET status='skipped', last_error='починка: битое название' WHERE id=? AND status='pending_review'", (mid[0],))
    print("снято:", n)
