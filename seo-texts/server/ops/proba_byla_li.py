# -*- coding: utf-8 -*-
"""Гонялись ли отправляемые адреса через пробу и был ли выбор получше."""
import io
import json
import sqlite3
from collections import Counter, defaultdict

партии = {}
for ф in (r"C:\sender\_ops\vtorye-adresa.jsonl", r"C:\sender\_ops\vtorye-adresa-2.jsonl"):
    try:
        for с in io.open(ф, encoding="utf-8"):
            d = json.loads(с)
            if "review" in d:
                партии[d["email"].lower()] = (int(d["review"]), str(d["inn"]))
    except FileNotFoundError:
        pass
почты = sorted(партии)
e = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\enrich.db", uri=True, timeout=60)
e.row_factory = sqlite3.Row
был = Counter()
для = {}
for i in range(0, len(почты), 400):
    к = почты[i:i + 400]
    зн = ",".join("?" * len(к))
    for r in e.execute("SELECT email, probe_verdict, probe_ts FROM emails "
                       " WHERE email IN (%s)" % зн, к):
        а = (r["email"] or "").lower()
        if r["probe_ts"]:
            для[а] = (r["probe_verdict"], str(r["probe_ts"])[:10])
for а in почты:
    был["проба была: " + (для[а][0] or "?") if а in для else "пробы НЕ было"] += 1
print("адресов в партиях: %d" % len(почты))
for к, n in был.most_common():
    print("   %-34s %5d  (%.0f%%)" % (к, n, 100.0 * n / len(почты)))
дни = Counter(v[1] for v in для.values())
print("")
print("=== когда пробовали (топ дней) ===")
for д, n in дни.most_common(6):
    print("   %s  %5d" % (д, n))

# был ли у компании адрес получше — с вердиктом «есть»
инны = sorted({v[1] for v in партии.values()})
лучше = defaultdict(list)
for i in range(0, len(инны), 400):
    к = инны[i:i + 400]
    зн = ",".join("?" * len(к))
    for r in e.execute("SELECT inn, email, probe_verdict, role FROM emails "
                       " WHERE inn IN (%s) AND probe_verdict='есть'" % зн, к):
        лучше[str(r["inn"])].append(((r["email"] or "").lower(), r["role"] or "—"))
e.close()
ПОЧТОВИКИ = {"mail.ru", "inbox.ru", "list.ru", "bk.ru", "yandex.ru", "ya.ru",
             "gmail.com", "rambler.ru", "internet.ru", "narod.ru", "outlook.com",
             "hotmail.com", "icloud.com", "yahoo.com", "tut.by"}
взято_слабое = 0
примеры = []
for а, (rev, инн) in партии.items():
    в = (для.get(а) or ("", ""))[0]
    if в != "принимает всё":
        continue
    дом = а.split("@", 1)[1]
    # альтернатива годится, только если она НА ТОМ ЖЕ корпоративном домене:
    # адрес на yandex.ru отбор и не должен брать, это не «лучший выбор»
    альт = [x for x in лучше.get(инн, [])
            if x[0] != а and x[0].split("@", 1)[-1] == дом
            and дом not in ПОЧТОВИКИ]
    if альт:
        взято_слабое += 1
        if len(примеры) < 6:
            примеры.append((инн, а, альт[0][0], альт[0][1]))
print("")
print("=== был ли выбор получше ===")
print("взяли «принимает всё», хотя у компании есть адрес с вердиктом «есть»: %d"
      % взято_слабое)
for инн, а, б, р in примеры:
    print("   %-13s взяли %-28s а был %-28s (%s)" % (инн, а[:28], б[:28], р))
