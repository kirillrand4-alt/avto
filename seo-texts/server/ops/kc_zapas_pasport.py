# -*- coding: utf-8 -*-
"""Владелец 17.11: «паспорт компании у скольки есть?» — по запасу CA-ENGER (без карточки КЦ, модель газа не смотрела).
Паспорт = поля сайта в CA-ENGER-BAZA-kompanii.csv (Продукция, Оборудование, Мощности…) и/или site_facts в enrich.db.
Только чтение."""
import csv, io, json, os, re, sqlite3
from collections import Counter
csv.field_size_limit(10 ** 9)
ДР = r"C:\seostat\drop\drop-storage"; ц = lambda x: "".join(c for c in str(x or "") if c.isdigit())
чит = lambda и: list(csv.DictReader(io.open(os.path.join(ДР, и), encoding="utf-8-sig", errors="replace"), delimiter=";"))
ПОЛЯ = ["Продукция", "Оборудование, линии", "Мощности", "Сырьё", "Упаковка, фасовка", "Контроль качества", "Масштаб",
        "Год основания", "Экспорт", "География поставок", "Клиенты", "Энергохозяйство", "Газы (паспорт)", "Расширение"]
БАЗА = {ц(р["ИНН"]): р for р in чит("CA-ENGER-BAZA-kompanii.csv")}
к = sqlite3.connect(r"file:C:\sender\sender.db?mode=ro", uri=True)
кам = {i: н for i, н in к.execute("SELECT id, name FROM campaigns")}
кц = {i for i, н in кам.items() if re.search(r"(?i)кц|компрессор|\bkc\b", н or "") and not re.search(r"(?i)meyer|мейер|фса|рентген|сепарат", н or "")}
карт = {ц(i) for i, кид in к.execute("SELECT inn, campaign_id FROM confirm_reviews") if кид in кц}
ответ = {ц(r[0]) for r in к.execute("SELECT DISTINCT r.inn FROM events e JOIN recipients r ON r.id=e.recipient_id WHERE e.event_type IN ('reply','complaint','unsubscribe')")}
суд = set()
for с in io.open(r"C:\sender\_ops\gaz-kc-sud.jsonl", encoding="utf-8", errors="replace"):
    try: суд.add(ц(json.loads(с).get("inn")))
    except Exception: pass
e = sqlite3.connect(r"file:C:\sender\enrich.db?mode=ro", uri=True)
def вес_sf(f):
    n = 0
    for k in ("продукция", "сырьё", "упаковка_фасовка", "мощности", "контроль_качества", "экспорт", "оборудование_линии", "география_поставок", "масштаб", "год_основания"):
        v = f.get(k); n += len(v) if isinstance(v, (list, tuple)) else (1 if v else 0)
    return n
SF = {}
for i, fj in e.execute("SELECT inn, facts_json FROM site_facts"):
    try: f = json.loads(fj or "{}")
    except Exception: continue
    if isinstance(f, dict): SF[ц(i)] = вес_sf(f)
for имя in ("CA-ENGER-ZALIVKA-kompanii.csv", "CA-ENGER-BAZA-kompanii.csv"):
    s = {ц(р["ИНН"]) for р in чит(имя)} - карт - ответ - суд - {""}
    сч = Counter()
    for и in s:
        р = БАЗА.get(и, {}); n = sum(1 for п in ПОЛЯ if (р.get(п) or "").strip())
        сч["полей паспорта 0" if n == 0 else ("1-2" if n <= 2 else ("3-5" if n <= 5 else "6+"))] += 1
        сч["есть «Продукция»"] += bool((р.get("Продукция") or "").strip())
        сч["есть сайт"] += bool((р.get("Сайт") or "").strip())
        сч["site_facts в enrich"] += и in SF; сч["site_facts вес>=8"] += SF.get(и, 0) >= 8
        сч["паспорт есть (поля ≥3 или site_facts ≥8)"] += (n >= 3 or SF.get(и, 0) >= 8)
    print("== %s: в запасе %d" % (имя, len(s)))
    for кл in ("полей паспорта 0", "1-2", "3-5", "6+", "есть сайт", "есть «Продукция»", "site_facts в enrich", "site_facts вес>=8", "паспорт есть (поля ≥3 или site_facts ≥8)"):
        print("   %-44s %d" % (кл, сч[кл]))
