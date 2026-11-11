# -*- coding: utf-8 -*-
"""Кому писал Meyer (владелец 11.11: «дай список инн кому мы писали по мейер + сайт + контакт, положи на дроп»).
send_log outcome='sent' по кампаниям Meyer (по названию). Одна строка на ИНН: компания, сайт (enrich → домен
адреса), адреса, писем, первое/последнее, кампании. Пишет CSV прямо в хранилище дропа MEYER-PISALI.csv.
Только чтение баз."""
import csv, io, os, re, sqlite3
from collections import defaultdict
s = sqlite3.connect("file:C:\\sender\\sender.db?mode=ro", uri=True, timeout=60)
e = sqlite3.connect("file:C:\\sender\\enrich.db?mode=ro", uri=True, timeout=60)
РЕ = re.compile(r"(?i)meyer|мейер|фса|рентген|сепарат")
камп = {i: н for i, н in s.execute("SELECT id, name FROM campaigns") if РЕ.search(н or "")}
print("кампании Meyer:", sorted(камп.items()))
по = defaultdict(lambda: {"адреса": set(), "n": 0, "первое": "", "последнее": "", "камп": set()})
for inn, em, cid, ts in s.execute("SELECT inn, lower(email), campaign_id, ts FROM send_log WHERE outcome='sent'"):
    if cid not in камп: continue
    и = re.sub(r"\D", "", str(inn or "")) or "(без ИНН)"
    д = по[и]; д["адреса"].add(em or ""); д["n"] += 1; д["камп"].add(камп[cid])
    if not д["первое"] or ts < д["первое"]: д["первое"] = ts
    if ts > д["последнее"]: д["последнее"] = ts
# РОЛИ (владелец 11.11: «добавь роли адресам, которые у нас в панели за ними были записаны») — панель показывает
# роль из enrich.db/emails; берём запись того же ИНН, иначе любую непустую по адресу.
роль = {}
for em, inn, р in e.execute("SELECT lower(email), inn, role FROM emails WHERE role IS NOT NULL AND role<>''"):
    и_ = re.sub(r"\D", "", str(inn or ""))
    роль.setdefault((em, и_), р); роль.setdefault((em, ""), р)
def с_ролью(em, и):
    р = роль.get((em, и)) or роль.get((em, ""))
    return "%s (%s)" % (em, р) if р else em
имя_р = {}
for inn, cn in s.execute("SELECT inn, company_name FROM recipients WHERE inn IS NOT NULL AND company_name IS NOT NULL"):
    имя_р.setdefault(re.sub(r"\D", "", str(inn)), cn)
п = r"C:\seostat\drop\drop-storage\MEYER-PISALI.csv"
with io.open(п, "w", encoding="utf-8-sig", newline="") as ф:
    w = csv.writer(ф, delimiter=";")
    w.writerow(["ИНН", "Компания", "Сайт", "Контакты (кому писали) — адрес (роль в панели)", "Писем", "Первое", "Последнее", "Кампании"])
    for и, д in sorted(по.items(), key=lambda x: -x[1]["n"]):
        r = e.execute("SELECT name, site FROM companies WHERE inn=?", (и,)).fetchone() if и.isdigit() else None
        сайт = (r[1] if r and r[1] else "") or ""
        if not сайт:
            дом = sorted({a.split("@")[-1] for a in д["адреса"] if "@" in a} - {"mail.ru", "yandex.ru", "gmail.com", "bk.ru", "list.ru", "inbox.ru", "ya.ru", "rambler.ru"})
            сайт = (дом[0] + " (по домену почты)") if дом else ""
        w.writerow([и, (r[0] if r and r[0] else имя_р.get(и, "")), сайт, ", ".join(с_ролью(a, и) for a in sorted(д["адреса"])), д["n"],
                    д["первое"][:10], д["последнее"][:10], "; ".join(sorted(д["камп"]))])
print("адресов с ролью:", sum(1 for д in по.values() for a in д["адреса"] if роль.get((a, "")))) 
print("ИНН: %d, адресов: %d, писем: %d -> %s" % (len(по), sum(len(д["адреса"]) for д in по.values()), sum(д["n"] for д in по.values()), п))
