# -*- coding: utf-8 -*-
"""Сколько из отобранных вторых адресов отвечает правилу владельца:
паспорт сайта совпадает с доменом почты ЛИБО почта взята с этого сайта,
И выручка от 30 млн."""
import re
import sqlite3
import sys
from collections import Counter

sys.path.insert(0, r"C:\sender\sender")
exec(open(r"C:\sender\server\ops\zapas_kopiy_3dnya.py", encoding="utf-8")
     .read().split("print(\"\")\nprint(\"=== отсев адресов ===\")")[0])
выбор = {инн: sorted(v)[0] for инн, v in годные.items()}
ПОРОГ = float(next((a.split("=")[1] for a in sys.argv if a.startswith("vyruchka=")),
                   "30")) * 1e6
print("")
print("отобрано: %d, порог выручки: %.0f млн" % (len(выбор), ПОРОГ / 1e6))

def дом(u):
    u = str(u or "").strip().lower()
    м = re.search(r"//([^/]+)", u)
    d = м.group(1) if м else u.split("/")[0]
    d = d[4:] if d.startswith("www.") else d
    return d if "." in d else ""

инны = sorted(выбор)
e = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\enrich.db", uri=True, timeout=90)
e.row_factory = sqlite3.Row
паспорт = {}          # инн -> {домены паспорта}
for i in range(0, len(инны), 400):
    к = инны[i:i + 400]; зн = ",".join("?" * len(к))
    for r in e.execute("SELECT inn, site, sources_json FROM site_facts "
                       " WHERE inn IN (%s) AND COALESCE(facts_json,'')<>''" % зн, к):
        д = дом(r["site"])
        if д:
            паспорт.setdefault(str(r["inn"]), set()).add(д)
        for u in re.findall(r"https?://[^\s\"']+", str(r["sources_json"] or ""))[:20]:
            д2 = дом(u)
            if д2:
                паспорт.setdefault(str(r["inn"]), set()).add(д2)
# откуда взят адрес
откуда = {}
for i in range(0, len(инны), 400):
    к = инны[i:i + 400]; зн = ",".join("?" * len(к))
    for r in e.execute("SELECT inn, email, source, source_url FROM emails "
                       " WHERE inn IN (%s)" % зн, к):
        откуда[(str(r["inn"]), (r["email"] or "").lower())] = (
            str(r["source"] or ""), дом(r["source_url"]))
# выручка
выр = {}
ob = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\obzvon-index.db", uri=True, timeout=60)
for i in range(0, len(инны), 400):
    к = инны[i:i + 400]; зн = ",".join("?" * len(к))
    for r in ob.execute("SELECT inn, revenue_rub FROM obzvon WHERE inn IN (%s)" % зн, к):
        try:
            в = float(r[1])
        except Exception:                                       # noqa: BLE001
            continue
        if в > 0:
            выр.setdefault(str(r[0]), в)
ob.close()
нет = [и for и in инны if и not in выр]
for i in range(0, len(нет), 400):
    к = нет[i:i + 400]; зн = ",".join("?" * len(к))
    for r in e.execute("SELECT inn, revenue_rub FROM companies WHERE inn IN (%s)" % зн, к):
        try:
            в = float(r[1])
        except Exception:                                       # noqa: BLE001
            continue
        if в > 0:
            выр.setdefault(str(r[0]), в)
e.close()

сч = Counter()
годно = []
for инн, v in выбор.items():
    адрес = v[3]
    д_почты = адрес.split("@", 1)[1]
    пас = паспорт.get(инн) or set()
    ист, д_ист = откуда.get((инн, адрес), ("", ""))
    совпал = д_почты in пас
    с_сайта = bool(д_ист) and (д_ист in пас or д_ист == д_почты)
    в = выр.get(инн, 0.0)
    сч["паспорта нет вовсе"] += 0 if пас else 1
    if not (совпал or с_сайта):
        сч["домен почты не из паспорта"] += 1
        continue
    сч["домен сошёлся" if совпал else "адрес взят с сайта паспорта"] += 1
    if not в:
        сч["выручка неизвестна"] += 1
        continue
    if в < ПОРОГ:
        сч["выручка ниже порога"] += 1
        continue
    сч["ПОДХОДИТ"] += 1
    годно.append((инн, адрес, в))
print("")
print("=== правило: паспорт+выручка ===")
for к, n in сч.most_common():
    print("   %-34s %5d" % (к, n))
if годно:
    годно.sort(key=lambda x: -x[2])
    print("")
    print("медиана выручки подходящих: %s"
          % "{:,.0f}".format(годно[len(годно) // 2][2]).replace(",", " "))
    print("верхние пять:")
    for и, а, в in годно[:5]:
        print("   %-13s %-30s %s" % (и, а[:30], "{:,.0f}".format(в).replace(",", " ")))
