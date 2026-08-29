# -*- coding: utf-8 -*-
"""Итог: что теперь известно про компании со сделкой."""
import sqlite3
from collections import Counter


def цифры(з):
    return "".join(c for c in str(з or "") if c.isdigit())


c = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\sender.db", uri=True,
                    timeout=60)
сделки = {цифры(r[0]) for r in c.execute(
    "SELECT value FROM suppression WHERE reason='deal_in_progress' "
    "  AND scope='inn'")}
сделки.discard("")
c.close()
e = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\enrich.db", uri=True,
                    timeout=60)
e.row_factory = sqlite3.Row
рек = {}
for r in e.execute("SELECT inn, ogrn, okved_main, status, name_short, address "
                   "  FROM requisites WHERE COALESCE(ogrn,'')<>''"):
    и = цифры(r["inn"])
    if и:
        рек[и] = r
комп = {цифры(r[0]) for r in e.execute("SELECT inn FROM companies")}
e.close()
есть = сделки & set(рек)
print("компаний со сделкой:            %d" % len(сделки))
print("с карточкой ЕГРЮЛ в requisites: %d (%.1f%%)"
      % (len(есть), 100.0 * len(есть) / len(сделки)))
print("из них было в companies раньше: %d" % len(есть & комп))
print("НОВЫХ для наших баз:            %d" % len(есть - комп))
ст = Counter(str(рек[и]["status"] or "?") for и in есть)
print("статус: %s" % dict(ст.most_common()))
с_оквэд = sum(1 for и in есть if str(рек[и]["okved_main"] or "").strip())
print("с ОКВЭД: %d, с адресом: %d, с названием: %d"
      % (с_оквэд,
         sum(1 for и in есть if str(рек[и]["address"] or "").strip()),
         sum(1 for и in есть if str(рек[и]["name_short"] or "").strip())))
print("\nвсего строк в requisites с ОГРН: %d" % len(рек))
