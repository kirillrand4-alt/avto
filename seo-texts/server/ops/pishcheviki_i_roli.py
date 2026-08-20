# -*- coding: utf-8 -*-
"""Пищевые компании и контакты по ролям под вебинар.

Владелец 20.08 уточнил: «кому писали тоже можно, это другая тема».
Значит фильтр «холодные» снимается — считаем всех.
"""
import re
import sqlite3
from collections import Counter

ОБЗВОН = r"C:\sender\obzvon-index.db"
ПАНЕЛЬ = r"C:\sender\sender.db"
ENRICH = r"C:\sender\enrich.db"


def ро(п):
    return sqlite3.connect("file:%s?mode=ro" % п.replace("\\", "/"), uri=True)


o, p, e = ро(ОБЗВОН), ро(ПАНЕЛЬ), ро(ENRICH)
o.row_factory = sqlite3.Row

приговор = {str(r[0]).lower() for r in p.execute(
    "SELECT email FROM addr_probe WHERE verdict IN ('нет ящика','нет MX')")}
стоп = {str(r[0]).lower() for r in p.execute("SELECT value FROM suppression")}

# Люди с ролями: где есть почта — тем можно писать лично.
роли_инн = {}
for таб in ("imena", "people"):
    try:
        for r in e.execute(f"SELECT inn, role, COALESCE(email,'') em FROM {таб}"):
            инн = str(r[0] or "")
            роль = str(r[1] or "").lower()
            if not инн or not роль:
                continue
            д = роли_инн.setdefault(инн, {"роли": set(), "с_почтой": set()})
            д["роли"].add(роль)
            if str(r[2] or "").strip():
                д["с_почтой"].add(роль)
    except Exception as ex:                                      # noqa: BLE001
        print(f"  таблица {таб} не прочлась: {str(ex)[:70]}")

ЦЕЛЕВЫЕ = ("качеств", "технолог", "инженер", "производств", "директор",
           "главный", "гл.")
КФХ_ИМЯ = re.compile(r"(?i)\bкфх\b|крестьян|фермерск|глава\s+к\(ф\)х")


def почты(r):
    из_ = []
    for поле in ("emails_base", "emails_site"):
        for a in re.split(r"[;,\s]+", str(r[поле] or "")):
            a = a.strip().lower()
            if "@" in a and "." in a.split("@")[-1]:
                из_.append(a)
    return sorted(set(из_))


гр = Counter()
адресов = Counter()
с_ролью = Counter()
с_личной = Counter()
for r in o.execute(
        "SELECT inn, name_short, name_full, opf, okved_main, okved_all_codes, "
        "       emails_base, emails_site FROM obzvon"):
    ок = str(r["okved_main"] or "").strip()
    к2 = ок[:2]
    if к2 not in ("10", "11"):
        continue
    имя = f"{r['name_short'] or ''} {r['name_full'] or ''} {r['opf'] or ''}"
    if КФХ_ИМЯ.search(имя) or str(r["okved_all_codes"] or "").startswith("01."):
        гр["КФХ — исключено"] += 1
        continue
    группа = "10.x производство еды" if к2 == "10" else "11.x напитки"
    живые = [a for a in почты(r) if a not in приговор and a not in стоп]
    if not живые:
        гр[f"{группа}: без живой почты"] += 1
        continue
    гр[группа] += 1
    адресов[группа] += len(живые)
    д = роли_инн.get(str(r["inn"] or "")) or {}
    if any(any(ц in роль for ц in ЦЕЛЕВЫЕ) for роль in д.get("роли", ())):
        с_ролью[группа] += 1
    if any(any(ц in роль for ц in ЦЕЛЕВЫЕ) for роль in д.get("с_почтой", ())):
        с_личной[группа] += 1

print("== под рассылку (без КФХ, с живой почтой) ==")
всего = адр = 0
for г in ("10.x производство еды", "11.x напитки"):
    print(f"  {гр[г]:>7} компаний | {адресов[г]:>7} адресов | "
          f"{с_ролью[г]:>6} с известной ролью | {с_личной[г]:>5} с личной почтой"
          f"  — {г}")
    всего += гр[г]
    адр += адресов[г]
print(f"  {всего:>7} компаний | {адр:>7} адресов — ИТОГО")
print("\n== отсеяно ==")
for k, n in гр.most_common():
    if "без живой почты" in k or "КФХ" in k:
        print(f"  {n:>7}  {k}")
