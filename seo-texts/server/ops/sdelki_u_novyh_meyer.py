# -*- coding: utf-8 -*-
"""Новые Meyer-компании (предкласс вне групп 14.10 / группа «Meyer вне групп 14.10»):
были ли с ними сделки в Битриксе (любые: активные, провальные, успешные; Meyer/КЦ/СЦ).
Владелец: «пытаюсь понять почему раньше не писали им». Только чтение."""
import io
import json
import sqlite3
from collections import Counter

д = json.load(io.open(r"C:\seostat\drop\drop-storage\sdelki-vse-1410.json", encoding="utf-8"))
c = sqlite3.connect(r"C:\sender\sender.db", timeout=30)
e = sqlite3.connect(r"C:\sender\enrich.db", timeout=30)
инн = {str(r[0]) for r in c.execute("SELECT inn FROM recipients WHERE extra_json LIKE '%Meyer вне групп 14.10%'")}
инн |= {str(r[0]) for r in e.execute("SELECT inn FROM companies WHERE verdikt_pochemu LIKE '%вне групп 14.10%' "
                                      "AND verdikt_napr IN ('мейер','оба')")}
инн = {"".join(ч for ч in i if ч.isdigit()) for i in инн}
выручка = {str(r[0]): r[1] for r in e.execute("SELECT inn, revenue_rub FROM companies")}
св, по_типу, примеры = Counter(), Counter(), []
for i in инн:
    сд = д.get(i) or []
    if not сд:
        св["сделок не было вообще"] += 1
        continue
    акт = [s for s in сд if s[1] == "В работе"]
    напр = sorted({s[0] for s in сд})
    if акт:
        св["есть АКТИВНАЯ сделка"] += 1
        по_типу["активная: " + "+".join(sorted({s[0] for s in акт}))] += 1
    else:
        св["были сделки, все закрыты"] += 1
        по_типу["закрытые: " + "+".join(напр)] += 1
    if len(примеры) < 12 and "meyer" in напр:
        примеры.append((i, [s for s in сд if s[0] == "meyer"][:2]))
print("новых Meyer-компаний: %d" % len(инн))
for к, n in св.most_common():
    print("   %-32s %5d" % (к, n))
print("по направлениям сделок:")
for к, n in по_типу.most_common():
    print("   %-32s %5d" % (к, n))
print("примеры со сделками Meyer:")
for i, s in примеры:
    print("   %s выручка %s: %s" % (i, выручка.get(i), s))
print("=== СДЕЛКИ У НОВЫХ MEYER ===")
