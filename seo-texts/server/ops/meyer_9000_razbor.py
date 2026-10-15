# -*- coding: utf-8 -*-
"""Разбор компаний «Россия 9000» с вердиктом «мейер»: что с каждой. Только чтение."""
import glob, io, json, sqlite3, sys
from collections import Counter
sys.path.insert(0, r"C:\sender")
c = sqlite3.connect(r"C:\sender\sender.db", timeout=60)
e = sqlite3.connect(r"C:\sender\enrich.db", timeout=60)
напр = {str(r[0]): r[1] for r in e.execute("SELECT inn, verdikt_napr FROM companies")}
мёртв = {str(r[0]).lower() for r in c.execute("SELECT email FROM addr_probe WHERE verdict IN ('нет ящика','нет MX')")}
адр = {}
for inn, em in c.execute("SELECT inn, email FROM recipients WHERE inn IS NOT NULL AND email LIKE '%@%'"):
    адр.setdefault(str(inn), set()).add(em.strip().lower())
ст = {}
for inn, s in c.execute("SELECT r.inn, m.status FROM messages m JOIN recipients r ON r.id=m.recipient_id WHERE r.inn IS NOT NULL"):
    ст.setdefault(str(inn), set()).add(s)
ген = {}
for ф in sorted(glob.glob(r"C:\sender\_ops\gen-*.jsonl")):
    for стр in io.open(ф, encoding="utf-8", errors="replace"):
        if '"итог"' in стр:
            try: з = json.loads(стр)
            except ValueError: continue
            ген[str(з.get("inn") or "")] = (з.get("ок"), "; ".join(map(str, з.get("брак") or []))[:300].lower())
try:
    from sender.sdelki_napr import blok
except Exception: blok = None
сч, вид = Counter(), set()
for inn, ex in c.execute("SELECT inn, extra_json FROM recipients WHERE inn IS NOT NULL"):
    inn = str(inn)
    if "Россия 9000" not in str(ex or "") or inn in вид or напр.get(inn) != "мейер": continue
    вид.add(inn)
    s = ст.get(inn, set())
    if "sent" in s: k = "отправлено"
    elif s & {"pending_review","approved","scheduled","sending"}: k = "в очереди"
    elif s: k = "письмо снято/сбой: " + ",".join(sorted(s))
    elif inn in ген and not ген[inn][0]:
        т = ген[inn][1]
        k = ("брак: не покупатель" if "не покупатель" in т else "брак: отказ/сбой модели" if ("i can" in т or "json" in т or "упал" in т)
             else "брак: линза/технолог" if ("линз" in т or "технолог" in т) else "брак: гейт текста")
    elif not [a for a in адр.get(inn, ()) if a not in мёртв]: k = "нет живого адреса"
    elif blok and blok(c, inn, "meyer"): k = "сделка Meyer в работе"
    else: k = "не генерировали (вне порций / упёрлись в порог цены)"
    сч[k] += 1
print("всего с вердиктом мейер:", len(вид))
for k, v in сч.most_common(): print("%6d  %s" % (v, k))
