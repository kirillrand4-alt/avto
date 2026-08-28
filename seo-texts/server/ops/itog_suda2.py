# -*- coding: utf-8 -*-
import io, json, sqlite3
from collections import Counter
в = {}
for с in io.open(r"C:\sender\_ops\sud-vtoryh-2.jsonl", encoding="utf-8"):
    try:
        d = json.loads(с)
        в[int(d["id"])] = d
    except Exception:
        pass
print("строк в следе с повторами, уникальных карточек: %d" % len(в))
партия = set()
for с in io.open(r"C:\sender\_ops\vtorye-adresa-2.jsonl", encoding="utf-8"):
    d = json.loads(с)
    if "review" in d:
        партия.add(int(d["review"]))
print("во второй партии карточек: %d, из них отсужено: %d"
      % (len(партия), len(партия & set(в))))
свои = {i: d for i, d in в.items() if i in партия}
print("")
print("=== вердикты второй партии ===")
for к, n in Counter(str(d.get("verdikt")) for d in свои.values()).most_common():
    print("   %-16s %4d  (%.0f%%)" % (к, n, 100.0 * n / max(1, len(свои))))
print("")
print("=== признаки (сколько ПЛОХО) ===")
for поле, имя in (("fakty_verny", "факты неверны"), ("napravlenie_verno", "направление не то"),
                  ("vopros_est", "нет вопроса"), ("obrashchenie_ok", "обращение не то"),
                  ("yazyk_ok", "язык корявый")):
    print("   %-22s %4d" % (имя, sum(1 for d in свои.values() if d.get(поле) is False)))
print("   %-22s %4d" % ("реклама", sum(1 for d in свои.values() if d.get("reklama") is True)))
print("   %-22s %4d" % ("выдумки", sum(1 for d in свои.values()
                                       if (d.get("vydumka") or "").strip())))
c = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\sender.db", uri=True, timeout=60)
зн = ",".join("?" * len(партия))
print("")
print("=== статусы второй партии ===")
for r in c.execute("SELECT status, COUNT(*) FROM confirm_reviews "
                   " WHERE id IN (%s) GROUP BY 1 ORDER BY 2 DESC" % зн, list(партия)):
    print("   %-12s %5d" % (r[0], r[1]))
c.close()
