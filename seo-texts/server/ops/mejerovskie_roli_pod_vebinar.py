# -*- coding: utf-8 -*-
"""Кому из мейеровской базы можно написать про вебинар: люди с ролями.

Владелец: «отбери для карточек мейера вот эти роли… желательно
отправлять специалистам по кач-ву, технологам, инженерам, ЛПР».

Смотрим, что реально есть: таблицы people/imena в обогащении держат
человека, должность, роль и иногда почту. Без почты человек нам не
адресат - писать некуда.
"""
import re
import sqlite3
from collections import Counter

ЦЕЛЕВЫЕ = ("качеств", "технолог", "инженер", "производств", "директор",
           "главный", "гл.", "начальник", "руководител", "снабжен", "закуп")
o = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\obzvon-index.db".replace(
    "\\", "/"), uri=True)
o.row_factory = sqlite3.Row
e = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\enrich.db".replace(
    "\\", "/"), uri=True)
p = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\sender.db".replace(
    "\\", "/"), uri=True)

приговор = {str(r[0]).lower() for r in p.execute(
    "SELECT email FROM addr_probe WHERE verdict IN ('нет ящика','нет MX')")}
стоп = {str(r[0]).lower() for r in p.execute("SELECT value FROM suppression")}

# Мейеровская база: division/base_label.
мейер = set()
разрез = Counter()
for r in o.execute("SELECT inn, COALESCE(division,'') d, "
                   "COALESCE(base_label,'') b, COALESCE(okved_main,'') ok "
                   "FROM obzvon"):
    метка = (str(r["d"]) + " " + str(r["b"])).lower()
    if "meyer" in метка or "мейер" in метка:
        мейер.add(str(r["inn"]))
        разрез[str(r["ok"])[:2]] += 1
print(f"компаний с мейеровской меткой: {len(мейер)}")
print("по группам ОКВЭД:", dict(разрез.most_common(6)))

люди = {}
for таб in ("imena", "people"):
    try:
        кол = [x[1] for x in e.execute(f"PRAGMA table_info([{таб}])")]
    except Exception:                                            # noqa: BLE001
        continue
    for r in e.execute(f"SELECT * FROM [{таб}]"):
        д = dict(zip(кол, r))
        инн = str(д.get("inn") or "")
        роль = (str(д.get("role") or "") + " " + str(д.get("post") or "")).lower()
        почта = str(д.get("email") or "").strip().lower()
        if инн not in мейер or not any(ц in роль for ц in ЦЕЛЕВЫЕ):
            continue
        д["_роль"] = роль.strip()
        люди.setdefault(инн, []).append(д)

с_почтой = 0
роли = Counter()
for инн, спис in люди.items():
    есть = [x for x in спис if str(x.get("email") or "").strip().lower()
            not in приговор | стоп and "@" in str(x.get("email") or "")]
    if есть:
        с_почтой += 1
    for x in спис:
        роли[str(x.get("role") or "?")] += 1

print(f"\nмейеровских компаний с человеком нужной роли: {len(люди)}")
print(f"из них с живой личной почтой: {с_почтой}")
print("\nроли:")
for р, n in роли.most_common(12):
    print(f"  {n:>4}  {р}")
