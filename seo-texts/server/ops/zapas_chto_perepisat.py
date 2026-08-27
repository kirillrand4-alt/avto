# -*- coding: utf-8 -*-
"""Что именно придётся переписать в 1116 телах: наше имя и обращение."""
import re
import sqlite3
import sys
from collections import Counter

sys.path.insert(0, r"C:\sender\sender")
exec(open(r"C:\sender\server\ops\zapas_kopiy_3dnya.py", encoding="utf-8")
     .read().split("print(\"\")\nprint(\"=== отсев адресов ===\")")[0])
выбор = {инн: sorted(v)[0] for инн, v in годные.items()}

c = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\sender.db", uri=True, timeout=90)
c.row_factory = sqlite3.Row
сч = Counter()
примеры = {"имя_вшито": [], "привет_с_именем": [], "подпись_в_теле": []}
инны = list(выбор)
for i in range(0, len(инны), 400):
    к = инны[i:i + 400]
    зн = ",".join("?" * len(к))
    for r in c.execute(
            "SELECT inn, body FROM confirm_reviews "
            " WHERE inn IN (%s) AND status IN ('approved','sent','pending') "
            "   AND COALESCE(body,'') <> ''" % зн, к):
        б = r["body"] or ""
        сч["тел всего"] += 1
        есть_зовут = bool(re.search(r"(?i)меня зовут", б))
        метка = "ИМЯ_ОТПРАВИТЕЛЯ" in б
        if есть_зовут and метка:
            сч["«меня зовут» + метка (движок подставит сам)"] += 1
        elif есть_зовут and not метка:
            сч["«меня зовут» с ВШИТЫМ именем - переписать"] += 1
            if len(примеры["имя_вшито"]) < 3:
                примеры["имя_вшито"].append(
                    (r["inn"], re.search(r"(?i)меня зовут[^.]{0,40}", б).group(0)))
        else:
            сч["без «меня зовут» (наше имя только в подписи)"] += 1
        if re.match(r"(?i)^\s*(добрый день|здравствуйте)\s*,", б):
            сч["приветствие с именем адресата - переписать"] += 1
            if len(примеры["привет_с_именем"]) < 3:
                примеры["привет_с_именем"].append(
                    (r["inn"], б.split("\n", 1)[0][:50]))
        if re.search(r"(?i)с уважением", б):
            сч["подпись уже вшита в тело"] += 1
            if len(примеры["подпись_в_теле"]) < 2:
                примеры["подпись_в_теле"].append((r["inn"], б[-90:].replace("\n", " | ")))
c.close()

print("")
print("=== что в телах ===")
for к, n in сч.most_common():
    print("   %-46s %5d" % (к, n))
for имя, сп in примеры.items():
    if сп:
        print("")
        print("   примеры «%s»:" % имя)
        for и, т in сп:
            print("      %-13s %s" % (и, т))
