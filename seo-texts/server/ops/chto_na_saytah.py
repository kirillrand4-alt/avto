# -*- coding: utf-8 -*-
"""Правду ли пишут письма: сверяем утверждения с текстом их сайтов."""
import json
import sqlite3

e = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\enrich.db", uri=True,
                    timeout=60)
e.row_factory = sqlite3.Row
s = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\sender.db", uri=True,
                    timeout=60)
s.row_factory = sqlite3.Row

for обзор, слова in ((12173, ("бесшовн", "сварн", "термообработ", "прокат",
                              "финишн", "нержаве")),
                     (12174, ("тепловыделя", "твэл", "керамик", "изостатич",
                              "молок", "соя", "зерн", "свин", "агро"))):
    q = s.execute("SELECT r.inn, r.company_name, r.domain FROM confirm_reviews c"
                  "  JOIN recipients r ON r.id=c.recipient_id WHERE c.id=?",
                  (обзор,)).fetchone()
    инн = q["inn"]
    print("\n######## %d  %s  ИНН %s  %s ########"
          % (обзор, q["company_name"], инн, q["domain"]))
    ф = e.execute("SELECT * FROM site_facts WHERE inn=?", (инн,)).fetchone()
    print("site_facts: %s" % ("есть" if ф else "НЕТ ЗАПИСИ"))
    if ф:
        for к in ф.keys():
            v = ф[к]
            if v and к not in ("inn",):
                print("   %-18s %s" % (к, str(v)[:220]))
    т = e.execute("SELECT * FROM site_text WHERE inn=?", (инн,)).fetchone()
    if not т:
        print("site_text: НЕТ ЗАПИСИ")
        continue
    текст = ""
    for к in т.keys():
        if isinstance(т[к], str) and len(т[к] or "") > len(текст):
            текст = т[к]
    print("site_text: %d знаков" % len(текст))
    низ = текст.lower()
    for сл in слова:
        n = низ.count(сл)
        print("   «%s»: %s" % (сл, ("встречается %d раз" % n) if n else "НЕ встречается"))
    print("   начало: %s" % текст[:300].replace("\n", " "))
e.close()
s.close()
