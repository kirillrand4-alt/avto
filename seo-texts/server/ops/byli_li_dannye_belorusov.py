# -*- coding: utf-8 -*-
"""Было ли в карточках занятие компании и дошло ли оно до генерации."""
import io
import json
import os
import sqlite3
from collections import Counter

КАРТОЧКИ = r"C:\sender\_ops\belarus\kartochki.jsonl"
РАЗБОР = r"C:\sender\_ops\belarus\katalog-razbor.jsonl"

# 1) что в карточках
поля_счёт = Counter()
карточки = []
if os.path.exists(КАРТОЧКИ):
    for с in io.open(КАРТОЧКИ, encoding="utf-8", errors="replace"):
        с = с.strip()
        if not с:
            continue
        try:
            k = json.loads(с)
        except Exception:                                      # noqa: BLE001
            continue
        карточки.append(k)
        for кл, v in k.items():
            if v not in (None, "", [], {}):
                поля_счёт[кл] += 1

занятие_ключи = [к for к in поля_счёт
                 if any(x in к.lower() for x in
                        ("занима", "деятель", "activity", "профил", "описан",
                         "продук", "чем"))]

print("=== КАРТОЧКИ КАТАЛОГА (%d) ===" % len(карточки))
print("заполненность полей:")
for к, в in поля_счёт.most_common(20):
    print("   %-22s %4d из %d" % (к, в, len(карточки)))
print("")
print("ключи про занятие: %s" % (занятие_ключи or "нет таких полей"))

print("")
print("--- ТРИ КАРТОЧКИ ЦЕЛИКОМ ---")
for k in карточки[:3]:
    print("   " + json.dumps(k, ensure_ascii=False)[:600])

# 2) дошло ли до панели
s = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\sender.db", uri=True,
                    timeout=120)
s.row_factory = sqlite3.Row
получ = [dict(r) for r in s.execute(
    "SELECT * FROM recipients WHERE inn LIKE '9990%' "
    "   OR COALESCE(extra_json,'') LIKE '%prodexpo%' LIMIT 5")]
s.close()

print("")
print("--- КАРТОЧКИ ПОЛУЧАТЕЛЕЙ В ПАНЕЛИ (что видит генератор) ---")
for р in получ:
    print("")
    print("   %s | %s" % (str(р.get("inn")), str(р.get("company_name"))[:40]))
    for к in ("okved", "activity", "extra_json", "site", "region"):
        if к in р and р[к] not in (None, ""):
            print("      %-12s %s" % (к, str(р[к])[:300]))

# 3) есть ли занятие в обогащении
e = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\enrich.db", uri=True,
                    timeout=120)
e.row_factory = sqlite3.Row
инны = [str(р.get("inn")) for р in получ]
print("")
print("--- ТЕ ЖЕ КОМПАНИИ В ОБОГАЩЕНИИ ---")
for и in инны:
    r = e.execute("SELECT inn, name, activity, okved, site, division "
                  "  FROM companies WHERE inn=?", (и,)).fetchone()
    if r:
        print("   %s | activity=%s | okved=%s | site=%s"
              % (и, str(r["activity"] or "—")[:60], str(r["okved"] or "—")[:20],
                 str(r["site"] or "—")[:30]))
    else:
        print("   %s — в companies НЕТ" % и)
e.close()
