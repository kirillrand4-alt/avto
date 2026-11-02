# -*- coding: utf-8 -*-
"""Судьба карточек второго касания из журнала _ops/lesenka-ochered-<id>.jsonl (только чтение).
    lesenka_sudba.py <id>"""
import io, json, sqlite3, sys
from collections import Counter
cid = sys.argv[1]
з = [json.loads(s) for s in io.open(r"C:\sender\_ops\lesenka-ochered-%s.jsonl" % cid, encoding="utf-8")]
c = sqlite3.connect("file:C:\\sender\\sender.db?mode=ro", uri=True, timeout=30)
сч = Counter(); причины = Counter()
for x in з:
    р = c.execute("SELECT cr.status, cr.reason, m.status, m.last_error FROM confirm_reviews cr LEFT JOIN messages m ON m.id=cr.message_id WHERE cr.id=?",
                  (x.get("review"),)).fetchone()
    if not р:
        сч["карточки нет (%s)" % x.get("status")] += 1
        continue
    сч["карточка %s / письмо %s" % (р[0], р[2])] += 1
    if р[2] != "sent":
        причины[str(р[1] or р[3] or "")[:70]] += 1
print("всего в журнале:", len(з))
for к, n in сч.most_common():
    print("  %5d  %s" % (n, к))
print("причины у неотправленных:")
for к, n in причины.most_common(10):
    print("  %5d  %s" % (n, к))
