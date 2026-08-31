# -*- coding: utf-8 -*-
"""Только чтение. Итоговый счёт по трём критериям владельца, с ПОЛНЫМ
набором «уже писали» (ai_letter_log через recipient_id + confirm_reviews)."""
import json
import sqlite3

ПОРОГ = 30_000_000


def норм(d):
    d = str(d or "").strip().lower()
    for п in ("https://", "http://"):
        if d.startswith(п):
            d = d[len(п):]
    d = d.split("/")[0].split("?")[0].split(":")[0]
    if d.startswith("www."):
        d = d[4:]
    return d.strip(". ")


e = sqlite3.connect("file:C:/sender/enrich.db?mode=ro", uri=True)
e.row_factory = sqlite3.Row
s = sqlite3.connect("file:C:/sender/sender.db?mode=ro", uri=True)
s.row_factory = sqlite3.Row

print("=== ai_letter_log: колонки ===")
кол = [r["name"] for r in s.execute("PRAGMA table_info(ai_letter_log)")]
print("  " + ", ".join(кол))

rid2inn = {}
for р in s.execute("SELECT id, inn FROM recipients"):
    rid2inn[р["id"]] = str(р["inn"] or "")

писали = set()
for р in s.execute("SELECT DISTINCT inn FROM confirm_reviews WHERE inn IS NOT NULL"):
    писали.add(str(р["inn"]))
n_cr = len(писали)
if "recipient_id" in кол:
    for р in s.execute("SELECT DISTINCT recipient_id FROM ai_letter_log"
                       " WHERE recipient_id IS NOT NULL"):
        i = rid2inn.get(р["recipient_id"])
        if i:
            писали.add(i)
print("  ИНН из confirm_reviews: %d; после ai_letter_log: %d (+%d)"
      % (n_cr, len(писали), len(писали) - n_cr))

паспорт = {}
for р in e.execute("SELECT inn, facts_json, site FROM site_facts"):
    try:
        f = json.loads(р["facts_json"] or "{}")
    except Exception:
        continue
    b = sum(1 for v in f.values() if v not in (None, "", [], {}, "нет"))
    if b:
        паспорт[str(р["inn"])] = (норм(р["site"]), b)
выручка = {}
for р in e.execute("SELECT inn, revenue_rub FROM companies WHERE revenue_rub IS NOT NULL"):
    try:
        выручка[str(р["inn"])] = float(р["revenue_rub"])
    except Exception:
        pass
источник = {}
for таб, кол2 in (("emails", "source_url"), ("email_sources", "url")):
    for р in e.execute("SELECT inn, email, %s u FROM %s" % (кол2, таб)):
        d = норм(р["u"])
        if d:
            источник.setdefault((str(р["inn"]), str(р["email"] or "").lower()), set()).add(d)

адресов = 0
инн, инн_св = set(), set()
блоки, выр = [], []
for р in s.execute("SELECT inn, email, domain FROM recipients WHERE segment='meyer'"):
    i, em, dom = str(р["inn"] or ""), str(р["email"] or "").lower(), норм(р["domain"])
    p = паспорт.get(i)
    if not p:
        continue
    сайт, b = p
    if not ((сайт and dom == сайт) or (сайт and сайт in источник.get((i, em), set()))):
        continue
    v = выручка.get(i)
    if v is None or v < ПОРОГ:
        continue
    адресов += 1
    инн.add(i)
    блоки.append(b)
    выр.append(v)
    if i not in писали:
        инн_св.add(i)

блоки.sort()
выр.sort()
print("\n=== ИТОГ: Meyer по трём критериям ===")
print("  адресов                       : %d" % адресов)
print("  УНИКАЛЬНЫХ КОМПАНИЙ           : %d" % len(инн))
print("  из них ещё НЕ писали          : %d" % len(инн_св))
print("  из них уже писали             : %d" % (len(инн) - len(инн_св)))
if блоки:
    print("  блоков паспорта: медиана %d, 10-90%% %d-%d"
          % (блоки[len(блоки) // 2], блоки[len(блоки) // 10], блоки[-max(1, len(блоки) // 10)]))
    print("  выручка, млн   : медиана %.0f, 10-90%% %.0f-%.0f"
          % (выр[len(выр) // 2] / 1e6, выр[len(выр) // 10] / 1e6,
             выр[-max(1, len(выр) // 10)] / 1e6))
