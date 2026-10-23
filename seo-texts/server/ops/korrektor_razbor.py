# -*- coding: utf-8 -*-
"""Разбор корректора (korrektor-kc1.jsonl): итоги, все правки; --otkat-plohih —
вернуть прежнее тело карточкам, где корректор тронул название/бренд (слово с
заглавной буквы или кавычки поменялись) — 23.10: «Компрессор Центре» → «компрессорном
центре». Только ещё не отправленные карточки. --otkat-vseh — вернуть все.
    korrektor_razbor.py [--otkat-plohih | --otkat-vseh]"""
import io
import json
import re
import sqlite3
import sys
from collections import Counter

з = [json.loads(s) for s in io.open(r"C:\sender\_ops\korrektor-kc1.jsonl", encoding="utf-8")]
print("записей:", len(з), Counter(str(x.get("итог"))[:40] for x in з).most_common())
плохие = []
for x in з:
    if x.get("итог") != "исправлено":
        continue
    пр = x.get("правки") or []
    подозр = any(re.search(r"[А-ЯЁA-Z«»\"]", п.split("→")[0]) and п.split("→")[0].strip() != п.split("→")[1].strip()
                 and (п.split("→")[0].strip()[:1].isupper() != п.split("→")[1].strip()[:1].isupper()
                      or "Центр" in п or "Руспром" in п or "Meyer" in п or "«" in п) for п in пр)
    print(("ПЛОХО " if подозр else "  ок  ") + "#%s: %s" % (x["review_id"], "; ".join(пр)[:220]))
    if подозр:
        плохие.append(x)
вернуть = плохие if "--otkat-plohih" in sys.argv else ([x for x in з if x.get("итог") == "исправлено"] if "--otkat-vseh" in sys.argv else [])
if вернуть:
    c = sqlite3.connect(r"C:\sender\sender.db", timeout=60)
    n = 0
    with c:
        for x in вернуть:
            n += c.execute("UPDATE confirm_reviews SET body=? WHERE id=? AND status IN ('pending','approved','edited')",
                           (x["было"], x["review_id"])).rowcount
    print("возвращено прежнее тело:", n)
