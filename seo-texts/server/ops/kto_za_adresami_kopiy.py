# -*- coding: utf-8 -*-
"""Есть ли в обогащении имя человека за адресом-копией.

Гадать имя по логину (evsvechnikova@ -> Свечникова?) в холодном письме
нельзя: ошибка в имени хуже отсутствия имени. Спрашиваем базу.
"""
import sqlite3
import sys

АДРЕСА = [a for a in sys.argv[1:] if "@" in a]
e = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\enrich.db".replace("\\", "/"),
                    uri=True)
e.row_factory = sqlite3.Row
for таб in ("people", "imena", "vne_bazy_emails"):
    try:
        кол = [x[1] for x in e.execute(f"PRAGMA table_info([{таб}])")]
    except Exception:                                            # noqa: BLE001
        continue
    if "email" not in кол:
        continue
    for а in АДРЕСА:
        for r in e.execute(f"SELECT * FROM [{таб}] WHERE lower(email)=?",
                           (а.lower(),)):
            д = dict(zip(кол, r))
            print(f"  {таб}: {а} -> {д.get('person')} | "
                  f"{д.get('post') or d if (d := д.get('role')) else ''}")
print("(пусто выше = имени за адресом в базе нет)")
