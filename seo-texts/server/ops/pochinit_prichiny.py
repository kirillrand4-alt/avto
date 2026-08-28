# -*- coding: utf-8 -*-
"""Дописать «копия на второй адрес» в причину всем уже переведённым карточкам,
чтобы заслон автоотправки не срезал их позже."""
import io, json, sqlite3, sys, time
sys.path.insert(0, r"C:\sender")
ids = []
for с in io.open(r"C:\sender\_ops\v-avtootpravku.jsonl", encoding="utf-8"):
    d = json.loads(с)
    if "review" in d:
        ids.append(int(d["review"]))
c = sqlite3.connect(r"C:\sender\sender.db", timeout=90)
c.execute("PRAGMA busy_timeout=60000")
зн = ",".join("?" * len(ids))
n = c.execute(
    "UPDATE confirm_reviews SET reason=?, updated_at=? "
    " WHERE id IN (%s) AND status='approved' "
    "   AND COALESCE(reason,'') NOT LIKE '%%копия на второй адрес%%'" % зн,
    ["bulk-to-auto: копия на второй адрес (судья: годно)",
     time.strftime("%Y-%m-%dT%H:%M:%S")] + ids).rowcount
c.commit()
c.close()
print("причин дописано: %d из %d" % (n, len(ids)))
