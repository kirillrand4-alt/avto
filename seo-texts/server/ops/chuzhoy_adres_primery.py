# -*- coding: utf-8 -*-
"""Примеры «адрес закреплён за другим ИНН» в генерации закупщиков: адрес, наша компания, чья в панели,
писали ли на адрес и когда. chuzhoy_adres_primery.py [N=15]"""
import collections, io, json, re, sqlite3, sys
N = int(sys.argv[1]) if len(sys.argv) > 1 else 15
s = sqlite3.connect("file:C:\\sender\\sender.db?mode=ro", uri=True, timeout=30)
e = sqlite3.connect("file:C:\\sender\\enrich.db?mode=ro", uri=True, timeout=30)
имя = lambda i: ((e.execute("SELECT name FROM companies WHERE inn=?", (i,)).fetchone() or [""])[0] or s.execute("SELECT company_name FROM recipients WHERE inn=? LIMIT 1", (i,)).fetchone() or [""])
рез = []; сч = collections.Counter()
for x in (json.loads(l) for l in io.open(r"C:\sender\_ops\zakupshchiki-kc.jsonl", encoding="utf-8")):
    if not str(x.get("otsev", "")).startswith("адрес закреплён"): continue
    чей = re.search(r"ИНН (\S+)", x["otsev"]).group(1)
    посл = s.execute("SELECT MAX(ts) FROM send_log WHERE outcome='sent' AND lower(email)=?", (x["email"],)).fetchone()[0]
    сч["писали на адрес" if посл else "не писали"] += 1
    дом_общий = x["email"].split("@")[1] in ("mail.ru", "yandex.ru", "bk.ru", "list.ru", "inbox.ru", "gmail.com", "ya.ru", "rambler.ru")
    сч["публичный домен" if дом_общий else "корпоративный домен"] += 1
    рез.append((x["email"], x["inn"], str(имя(x["inn"]))[:40], чей, str(имя(чей))[:40], (посл or "")[:10]))
print(dict(сч))
for r in рез[:N]: print("  %s | наша: %s %s | в панели: %s %s | писали: %s" % r)
