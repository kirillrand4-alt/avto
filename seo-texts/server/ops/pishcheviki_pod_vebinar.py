# -*- coding: utf-8 -*-
"""Пищевые компании под вебинар 28.08: сколько их, с почтой, холодных.

Границу «пищевик» показываем разрезом, а не решаем за владельца:
  10.x — производство пищевых продуктов (ядро)
  11.x — напитки
  46.3x — оптовая торговля едой и напитками (не производство)
КФХ исключаем тремя признаками сразу: ОПФ, название, ОКВЭД 01.x.
Холодной считаем компанию, которой ещё ни разу не писали (send_log по
ИНН и по всем её адресам).
"""
import re
import sqlite3
from collections import Counter

ОБЗВОН = r"C:\sender\obzvon-index.db"
ПАНЕЛЬ = r"C:\sender\sender.db"

o = sqlite3.connect("file:%s?mode=ro" % ОБЗВОН.replace("\\", "/"), uri=True)
o.row_factory = sqlite3.Row
p = sqlite3.connect("file:%s?mode=ro" % ПАНЕЛЬ.replace("\\", "/"), uri=True)

# Кому уже писали — по ИНН и по адресу.
писали_инн = {str(r[0]) for r in p.execute(
    "SELECT DISTINCT inn FROM send_log WHERE inn IS NOT NULL AND inn<>''")}
писали_почта = {str(r[0]).lower() for r in p.execute(
    "SELECT DISTINCT lower(email) FROM send_log WHERE email IS NOT NULL")}
print(f"уже писали: {len(писали_инн)} ИНН, {len(писали_почта)} адресов")

# Мёртвые адреса — их в рассылку класть нельзя.
приговор = {str(r[0]).lower() for r in p.execute(
    "SELECT email FROM addr_probe WHERE verdict IN ('нет ящика','нет MX')")}
стоп = {str(r[0]).lower() for r in p.execute(
    "SELECT value FROM suppression")}

КФХ_ИМЯ = re.compile(r"(?i)\bкфх\b|крестьян|фермерск|глава\s+к\(ф\)х")


def почты(r):
    из_ = []
    for поле in ("emails_base", "emails_site"):
        for a in re.split(r"[;,\s]+", str(r[поле] or "")):
            a = a.strip().lower()
            if "@" in a and "." in a.split("@")[-1]:
                из_.append(a)
    return sorted(set(из_))


счёт = Counter()
группы = Counter()
холодные_с_почтой = Counter()
for r in o.execute(
        "SELECT inn, name_short, name_full, opf, okved_main, "
        "       okved_all_codes, emails_base, emails_site, status, division "
        "FROM obzvon"):
    ок = str(r["okved_main"] or "").strip()
    код2 = ок[:2]
    if код2 not in ("10", "11") and not ок.startswith("46.3"):
        continue
    имя = f"{r['name_short'] or ''} {r['name_full'] or ''} {r['opf'] or ''}"
    if КФХ_ИМЯ.search(имя) or str(r["okved_all_codes"] or "").startswith("01."):
        счёт["КФХ — исключено"] += 1
        continue
    группа = ("10.x производство еды" if код2 == "10"
              else "11.x напитки" if код2 == "11"
              else "46.3x оптовая торговля едой")
    группы[группа] += 1
    ад = почты(r)
    живые = [a for a in ад if a not in приговор and a not in стоп]
    if not живые:
        счёт[f"{группа}: без живой почты"] += 1
        continue
    инн = str(r["inn"] or "")
    если_писали = inn_писали = инн in писали_инн or any(
        a in писали_почта for a in живые)
    if если_писали:
        счёт[f"{группа}: уже писали"] += 1
        continue
    холодные_с_почтой[группа] += 1

print("\n== всего в базе по группам ==")
for k, n in группы.most_common():
    print(f"  {n:>7}  {k}")
print(f"  {счёт['КФХ — исключено']:>7}  КФХ — исключено")

print("\n== холодные, с живой почтой ==")
всего = 0
for k, n in холодные_с_почтой.most_common():
    print(f"  {n:>7}  {k}")
    всего += n
print(f"  {всего:>7}  ИТОГО")

print("\n== что отсеялось ==")
for k, n in счёт.most_common():
    if k != "КФХ — исключено":
        print(f"  {n:>7}  {k}")
