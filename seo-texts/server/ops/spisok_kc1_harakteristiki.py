# -*- coding: utf-8 -*-
"""Характеристики списка генерации КЦ-1 (_ops/spisok-kc1.json) — владелец 21.10:
«скинь характеристики этих групп (паспорта, выручка)». Только чтение.
Разрезы: ИНН настоящий/синтетический, паспорт в обогащении (сколько полей),
выручка, отрасль (сегмент файла), проба адреса, ступень лесенки."""
import io
import json
import sqlite3
from collections import Counter

c = sqlite3.connect(r"C:\sender\sender.db")
e = sqlite3.connect(r"C:\sender\enrich.db")
ids = json.load(io.open(r"C:\sender\_ops\spisok-kc1.json"))
кол = [r[1] for r in e.execute("PRAGMA table_info(companies)")]
поля_паспорта = [k for k in ("activity", "site", "okved", "revenue_rub", "products", "equipment", "description", "passport_json",
                             "site_text", "profile") if k in кол]
комп = {str(r[0]): r for r in e.execute("SELECT inn, %s FROM companies" % ",".join(поля_паспорта))}
проба = {str(r[0]).lower(): str(r[1] or "") for r in c.execute("SELECT email, verdict FROM addr_probe")}
стр = c.execute("SELECT id, inn, lower(email), segment, extra_json FROM recipients WHERE id IN (%s)" % ",".join(map(str, ids))).fetchall()


def выр(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


сч = {k: Counter() for k in ("ИНН", "паспорт", "выручка", "отрасль", "проба", "ступень", "письмо")}
for rid, inn, em, seg, ex in стр:
    x = json.loads(ex or "{}")
    inn = str(inn or "")
    сч["ИНН"]["синтетический (найдены поиском)" if inn.startswith("000001") else "настоящий"] += 1
    р = комп.get(inn)
    n = sum(1 for v in (р[1:] if р else []) if v)
    сч["паспорт"]["нет строки в обогащении" if not р else "%d полей из %d" % (n, len(поля_паспорта))] += 1
    в = выр(x.get("revenue_rub")) or (выр(р[поля_паспорта.index("revenue_rub") + 1]) if р and "revenue_rub" in поля_паспорта else 0)
    сч["выручка"]["нет" if not в else "<100 млн" if в < 1e8 else "100-500 млн" if в < 5e8 else "500 млн-1 млрд" if в < 1e9
                  else "1-10 млрд" if в < 1e10 else ">10 млрд"] += 1
    сч["отрасль"][str(x.get("otrasl") or seg or "—").split("(")[0].strip()[:40]] += 1
    сч["проба"][проба.get(em, "") or "не проверен"] += 1
    сч["ступень"][str(x.get("stupen") or "—")[:30]] += 1
print("в списке:", len(ids), "| строк получателей:", len(стр))
print("поля паспорта в обогащении:", поля_паспорта)
for k, v in сч.items():
    print("\n== %s" % k)
    for кк, n in v.most_common(14):
        print("  %6d  %s" % (n, кк))
