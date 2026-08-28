# -*- coding: utf-8 -*-
import io, json, sqlite3
from collections import Counter
партия = {}
for с in io.open(r"C:\sender\_ops\vtorye-adresa.jsonl", encoding="utf-8"):
    d = json.loads(с); партия[int(d["review"])] = d["email"]
c = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\sender.db", uri=True, timeout=60)
зн = ",".join("?" * len(партия))
ст = dict(c.execute("SELECT status, COUNT(*) FROM confirm_reviews "
                    " WHERE id IN (%s) GROUP BY 1" % зн, list(партия)).fetchall())
print("статусы партии: %s" % ст)
print("")
print("=== причины снятия ===")
пр = Counter()
for r in c.execute("SELECT COALESCE(decided_by,'') FROM confirm_reviews "
                   " WHERE id IN (%s) AND status='skipped'" % зн, list(партия)):
    пр[r[0] or "—"] += 1
for к, n in пр.most_common():
    print("   %-40s %4d" % (к[:40], n))
c.close()
в = [json.loads(с) for с in io.open(r"C:\sender\_ops\sud-vtoryh.jsonl", encoding="utf-8")]
print("")
print("=== судья по всем 971 ===")
for к, n in Counter(str(x.get("verdikt")) for x in в).most_common():
    print("   %-16s %4d  (%.0f%%)" % (к, n, 100.0 * n / len(в)))
print("")
print("=== чем плохи «поправить» ===")
for поле, имя in (("fakty_verny", "факты неверны"), ("napravlenie_verno", "направление не то"),
                  ("vopros_est", "нет вопроса"), ("obrashchenie_ok", "обращение не то"),
                  ("yazyk_ok", "язык корявый")):
    print("   %-22s %4d" % (имя, sum(1 for x in в
                                     if x.get("verdikt") == "поправить" and x.get(поле) is False)))
print("   %-22s %4d" % ("реклама", sum(1 for x in в if x.get("verdikt") == "поправить"
                                       and x.get("reklama") is True)))
