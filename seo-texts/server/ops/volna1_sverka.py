# -*- coding: utf-8 -*-
"""Сверка файла FSA-MEYER-VOLNA1-500mln (выжимка volna1.json на дропе) с нашими
базами (владелец 21.10: «для Meyer есть полезное: уникальное, кому можем писать
+ новые адреса для тех, кому уже писали?»). Только чтение.

По компании: писал ли Meyer (send_log, кампании Meyer), отвечала ли (лиды),
активная сделка Meyer (sdelki_napr), стоп-лист. По адресам: новые (нет ни в
панели, ни в обогащении) и уже известные; кому из новых не писали.
Итог — _ops/volna1-sverka.json."""
import io
import json
import sqlite3
from collections import Counter

д = json.load(io.open(r"C:\seostat\drop\drop-storage\volna1.json", encoding="utf-8"))
c = sqlite3.connect(r"C:\sender\sender.db")
e = sqlite3.connect(r"C:\sender\enrich.db")
кам = {r[0]: r[1] for r in c.execute("SELECT id, name FROM campaigns")}
meyer = {k for k, v in кам.items() if "meyer" in str(v).lower() or "мейер" in str(v).lower()}
писал_m, писал_any = set(), set()
for inn, cid in c.execute("SELECT inn, campaign_id FROM send_log WHERE outcome='sent' AND inn IS NOT NULL"):
    писал_any.add(str(inn))
    if cid in meyer:
        писал_m.add(str(inn))
адр_писали = {str(r[0]).lower() for r in c.execute("SELECT email FROM send_log WHERE outcome='sent'")}
ответ = {str(r[0]) for r in c.execute("SELECT DISTINCT inn FROM leads WHERE inn IS NOT NULL")}
сделка = {str(r[0]) for r in c.execute("SELECT inn FROM sdelki_napr WHERE meyer=1")}
стоп_инн = {str(r[0]) for r in c.execute("SELECT value FROM suppression WHERE scope='inn'")} if True else set()
стоп_адр = {str(r[0]).lower() for r in c.execute("SELECT value FROM suppression WHERE scope='email'")}
стоп_дом = {str(r[0]).lower() for r in c.execute("SELECT value FROM suppression WHERE scope='domain'")}
известные = {str(r[0]).lower() for r in c.execute("SELECT email FROM recipients")} | {str(r[0]).lower() for r in e.execute("SELECT email FROM emails")}
проба = {str(r[0]).lower(): str(r[1] or "") for r in c.execute("SELECT email, verdict FROM addr_probe")}
адреса = {}
for к in д["cont"]:
    адреса.setdefault(к["inn"], []).append(к)
for к in д["comp"]:
    if к["best"] and not any(a["email"] == к["best"] for a in адреса.get(к["inn"], [])):
        адреса.setdefault(к["inn"], []).append({"inn": к["inn"], "email": к["best"], "role": к["role"], "step": к["step"]})
сч = Counter()
итог = []
for к in д["comp"]:
    inn = к["inn"]
    статус = ("ответила" if inn in ответ else "сделка Meyer" if (inn in сделка or к["deal"]) else "стоп-лист" if inn in стоп_инн
              else "Meyer уже писал" if inn in писал_m else "писал только КЦ" if inn in писал_any else "новая для Meyer")
    свои = адреса.get(inn, [])
    нов = [a for a in свои if a["email"] not in известные and a["email"] not in стоп_адр and a["email"].split("@")[-1] not in стоп_дом]
    нов_непис = [a for a in нов if a["email"] not in адр_писали]
    известн = [a for a in свои if a["email"] in известные]
    сч[(статус, "есть адреса" if свои else "нет адресов")] += 1
    итог.append({"inn": inn, "name": к["name"], "okved": к["okved"], "rev": к["rev"], "статус": статус,
                 "адресов": len(свои), "новых": len(нов_непис), "новые": [(a["email"], a.get("role"), a.get("step")) for a in нов_непис],
                 "известных": len(известн)})
json.dump(итог, io.open(r"C:\sender\_ops\volna1-sverka.json", "w", encoding="utf-8"), ensure_ascii=False)
print("компаний в файле:", len(д["comp"]))
for k, v in sorted(сч.items()):
    print("  %-22s %-12s %4d" % (k[0], k[1], v))
for ст in ("новая для Meyer", "писал только КЦ", "Meyer уже писал"):
    часть = [x for x in итог if x["статус"] == ст]
    print("%s: компаний %d, у них адресов в файле %d, из них НОВЫХ (нет в наших базах) %d у %d компаний" % (
        ст, len(часть), sum(x["адресов"] for x in часть), sum(x["новых"] for x in часть), sum(1 for x in часть if x["новых"])))
новые_все = [a for x in итог if x["статус"] in ("новая для Meyer", "писал только КЦ", "Meyer уже писал") for a in x["новые"]]
print("роли новых адресов:", Counter(str(a[1]) for a in новые_все).most_common(10))
print("проба новых (если уже есть):", Counter(проба.get(a[0], "не проверен") for a in новые_все).most_common())
print("ОКВЭД новых для Meyer компаний:", Counter(x["okved"][:2] for x in итог if x["статус"] == "новая для Meyer").most_common(8))
# Новые для Meyer: есть ли у нас свои адреса по ИНН (панель/обогащение), раз в файле нет.
по_инн = {}
for inn, em in c.execute("SELECT inn, lower(email) FROM recipients WHERE inn IS NOT NULL"):
    по_инн.setdefault(str(inn), set()).add(em)
for inn, em in e.execute("SELECT inn, lower(email) FROM emails"):
    по_инн.setdefault(str(inn), set()).add(em)
нов = [x for x in итог if x["статус"] == "новая для Meyer"]
без_файла = [x for x in нов if x["адресов"] == 0]
print("новые для Meyer без адресов в файле: %d, из них у нас в базах есть адрес: %d" % (
    len(без_файла), sum(1 for x in без_файла if по_инн.get(x["inn"]))))
print("новые для Meyer — всего с любым адресом (файл или наши базы): %d" % sum(1 for x in нов if x["адресов"] or по_инн.get(x["inn"])))
print("выручка новых для Meyer:", Counter(("нет" if not x["rev"] else "<1млрд" if float(x["rev"]) < 1e9 else "1-10млрд" if float(x["rev"]) < 1e10 else ">10млрд") for x in нов))
