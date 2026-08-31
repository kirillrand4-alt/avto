# -*- coding: utf-8 -*-
"""Из кого этот прогон пишет письма: свежезаведённые или давние карточки.

И главное — отличается ли у них процент брака. «Хорошо пошли» должно быть
замером, а не впечатлением.
"""
import json
import sqlite3
from collections import Counter

c = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\sender.db", uri=True,
                    timeout=60)
c.row_factory = sqlite3.Row

print("=== КОГДА ЗАВЕДЕНЫ ПОЛУЧАТЕЛИ ГРУППЫ «Партия 935» ===")
for r in c.execute("""SELECT substr(created_at,1,10) д, COUNT(*) n
      FROM recipients
     WHERE COALESCE(extra_json,'') LIKE '%Партия 935%'
     GROUP BY д ORDER BY д DESC LIMIT 12"""):
    print("   %s  %6d" % (r[0], r[1]))

print("\n=== ПИСЬМА ЭТОГО ПРОГОНА: ВОЗРАСТ КАРТОЧКИ ===")
строки = list(c.execute("""SELECT cr.id, cr.status, cr.reason, cr.inn,
              substr(r.created_at,1,10) заведён, r.company_name
         FROM confirm_reviews cr JOIN recipients r ON r.id=cr.recipient_id
        WHERE cr.campaign_id=11
          AND cr.created_at >= datetime('now','-2 hour')"""))
по_дате = Counter(s["заведён"] for s in строки)
print("   писем в очереди за прогон: %d" % len(строки))
for д, n in sorted(по_дате.items(), reverse=True)[:10]:
    print("      карточка заведена %s: %6d" % (д, n))

print("\n=== БРАК: СВЕЖИЕ ПРОТИВ ДАВНИХ ===")
# берём журнал прогона: там и брак, и ок
import io
import os
ЖУРНАЛ = r"C:\sender\_ops\gen-partiya-935.jsonl"
import time
порог = time.time() - 3 * 3600
свои = []
if os.path.exists(ЖУРНАЛ):
    for с in io.open(ЖУРНАЛ, encoding="utf-8"):
        try:
            z = json.loads(с)
        except Exception:                                     # noqa: BLE001
            continue
        т = z.get("ts")
        if isinstance(т, (int, float)) and т >= порог:
            свои.append(z)
print("   строк журнала за 3 часа: %d" % len(свои))
инн_даты = {}
for r in c.execute("SELECT inn, substr(created_at,1,10) д FROM recipients"
                   " WHERE inn IS NOT NULL"):
    и = str(r["inn"] or "")
    if и and и not in инн_даты:
        инн_даты[и] = r["д"]
свежие = Counter()
давние = Counter()
for z in свои:
    if z.get("этап") not in (None, "итог"):
        continue
    и = str(z.get("inn") or "")
    если_ок = "ок" if z.get("ок") else "брак"
    д = инн_даты.get(и, "")
    (свежие if д >= "2026-08-29" else давние)[если_ок] += 1
for имя, сч in (("заведены 29.08 и позже", свежие), ("заведены раньше", давние)):
    всего = sum(сч.values())
    if всего:
        print("   %-24s всего %4d, ок %4d (%.0f%%), брак %4d"
              % (имя, всего, сч["ок"], 100.0 * сч["ок"] / всего, сч["брак"]))

print("\n=== ПРИЧИНЫ БРАКА В ЭТОМ ПРОГОНЕ ===")
причины = Counter()
for s in строки:
    if s["status"] != "pending":
        причины[str(s["reason"] or "")[:60]] += 1
for п, n in причины.most_common(8):
    print("   %-62s %4d" % (п or "(без причины)", n))
c.close()

print("\n=== ИТОГ ===")
print("письма пишутся тем компаниям, чьи карточки заведены: %s"
      % ", ".join("%s — %d" % (д, n) for д, n in sorted(по_дате.items(),
                                                        reverse=True)[:4]))
