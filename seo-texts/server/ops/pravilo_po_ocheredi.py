# -*- coding: utf-8 -*-
"""Правило владельца по УЖЕ ПОСТАВЛЕННЫМ карточкам второго адреса:
домен почты = домен паспорта сайта ЛИБО адрес взят с этого сайта, И выручка
от порога (по умолчанию 30 млн)."""
import io
import json
import re
import sqlite3
import sys
from collections import Counter

ПОРОГ = float(next((a.split("=")[1] for a in sys.argv if a.startswith("vyruchka=")),
                   "30")) * 1e6
пары = []
for с in io.open(r"C:\sender\_ops\vtorye-adresa.jsonl", encoding="utf-8"):
    d = json.loads(с)
    пары.append((str(d["inn"]), d["email"].lower()))
инны = sorted({и for и, _ in пары})
print("карточек в очереди: %d, компаний: %d, порог: %.0f млн"
      % (len(пары), len(инны), ПОРОГ / 1e6))


def дом(u):
    u = str(u or "").strip().lower()
    м = re.search(r"//([^/]+)", u)
    d = м.group(1) if м else u.split("/")[0]
    d = d[4:] if d.startswith("www.") else d
    return d if "." in d else ""


e = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\enrich.db", uri=True, timeout=90)
e.row_factory = sqlite3.Row
паспорт, откуда = {}, {}
for i in range(0, len(инны), 400):
    к = инны[i:i + 400]; зн = ",".join("?" * len(к))
    for r in e.execute("SELECT inn, site, sources_json FROM site_facts "
                       " WHERE inn IN (%s) AND COALESCE(facts_json,'')<>''" % зн, к):
        for д in [дом(r["site"])] + [дом(u) for u in re.findall(
                r"https?://[^\s\"']+", str(r["sources_json"] or ""))[:20]]:
            if д:
                паспорт.setdefault(str(r["inn"]), set()).add(д)
    for r in e.execute("SELECT inn, email, source, source_url FROM emails "
                       " WHERE inn IN (%s)" % зн, к):
        откуда[(str(r["inn"]), (r["email"] or "").lower())] = (
            str(r["source"] or ""), дом(r["source_url"]))
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
годно, мимо = [], []
for инн, адрес in пары:
    д_почты = адрес.split("@", 1)[1]
    пас = паспорт.get(инн) or set()
    _ист, д_ист = откуда.get((инн, адрес), ("", ""))
    совпал = д_почты in пас
    с_сайта = bool(д_ист) and (д_ист in пас or д_ист == д_почты)
    в = выр.get(инн, 0.0)
    if not пас:
        сч["паспорта сайта нет"] += 1
        мимо.append((инн, адрес, "нет паспорта")); continue
    if not (совпал or с_сайта):
        сч["домен почты не из паспорта"] += 1
        мимо.append((инн, адрес, "домен мимо")); continue
    сч["домен сошёлся" if совпал else "адрес взят с сайта паспорта"] += 1
    if not в:
        сч["выручка неизвестна"] += 1
        мимо.append((инн, адрес, "выручка ?")); continue
    if в < ПОРОГ:
        сч["выручка ниже порога"] += 1
        мимо.append((инн, адрес, "мелкая")); continue
    сч["ПОДХОДИТ"] += 1
    годно.append((инн, адрес, в))
print("")
print("=== правило по очереди ===")
for к, n in сч.most_common():
    print("   %-34s %5d" % (к, n))
if годно:
    р = sorted(в for _, _, в in годно)
    print("")
    print("подходящих: %d из %d (%.0f%%), медиана выручки %s"
          % (len(годно), len(пары), 100.0 * len(годно) / len(пары),
             "{:,.0f}".format(р[len(р) // 2]).replace(",", " ")))
print("не прошли: %d" % len(мимо))
for к, n in Counter(x[2] for x in мимо).most_common():
    print("   %-16s %5d" % (к, n))
