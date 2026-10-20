# -*- coding: utf-8 -*-
"""Разрез списка второго касания Meyer: свой домен компании против публичного
почтовика, роли и проба по каждой части, примеры адресов."""
import io
import json
from collections import Counter
ПУБЛИЧНЫЕ = {"mail.ru", "bk.ru", "list.ru", "inbox.ru", "yandex.ru", "ya.ru", "gmail.com", "rambler.ru", "yandex.com"}
д = json.load(io.open(r"C:\sender\_ops\meyer-vtoroe-kasanie.json", encoding="utf-8"))
for имя, часть in (("свой домен", [x for x in д if x["кому"].split("@")[-1] not in ПУБЛИЧНЫЕ]),
                   ("публичный почтовик", [x for x in д if x["кому"].split("@")[-1] in ПУБЛИЧНЫЕ])):
    print("== %s: %d | проба %s" % (имя, len(часть), dict(Counter(x["проба"] for x in часть))))
    print("   роли:", Counter((x["роль"].split("|")[0].strip() or "без роли")[:25] for x in часть).most_common(8))
    print("   было на публичном:", sum(1 for x in часть if x["был_адрес"].split("@")[-1] in ПУБЛИЧНЫЕ))
    for x in часть[:6]:
        print("     %s -> %s (было %s)" % (x["inn"], x["кому"], x["был_адрес"]))
