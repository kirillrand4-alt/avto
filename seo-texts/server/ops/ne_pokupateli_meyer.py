# -*- coding: utf-8 -*-
"""Выгрузка «Meyer — не покупатель» из базы «наш или нет» (enrich.companies.verdikt_*):
направление кц / никуда / не мейер, или «не покупатель» Руспрома без направления Meyer.
«не кц» не берём: это отказ компрессорной линзы, про Meyer он ничего не говорит.
CSV (Excel: ; и utf-8-sig) — в _ops и на дроп, чтобы владелец убрал их из другой базы.

    ne_pokupateli_meyer.py
"""
import csv
import io
import re
import shutil
import sqlite3
import time
from collections import Counter, defaultdict
e = sqlite3.connect(r"C:\sender\enrich.db", timeout=30)
кол = [r[1] for r in e.execute("PRAGMA table_info(companies)")]
кн = next((k for k in ("name", "company_name", "naimenovanie", "nazvanie") if k in кол), None)
кс = next((k for k in ("site", "sayt", "website", "domain", "url") if k in кол), None)
print("колонки имени/сайта: %s / %s" % (кн, кс))
s = sqlite3.connect(r"C:\sender\sender.db", timeout=30)
имя, домены = {}, defaultdict(set)
for inn, n, em in s.execute("SELECT inn, company_name, email FROM recipients WHERE inn IS NOT NULL"):
    i = str(inn).strip()
    имя.setdefault(i, n or "")
    if em and "@" in em:
        домены[i].add(em.split("@")[1].lower())
ОБЩИЕ = {"mail.ru", "yandex.ru", "ya.ru", "gmail.com", "inbox.ru", "list.ru", "bk.ru", "rambler.ru", "yandex.by",
         "mail.by", "tut.by", "icloud.com", "outlook.com", "hotmail.com"}
поля = "inn, verdikt_rusprom, verdikt_napr, verdikt_pochemu, verdikt_istochnik, verdikt_ts" + \
       (", " + кн if кн else "") + (", " + кс if кс else "")
строки, св = [], Counter()
for р in e.execute("SELECT %s FROM companies WHERE verdikt_napr IN ('кц','никуда','не мейер') "
                   "OR (verdikt_rusprom='не покупатель' AND coalesce(verdikt_napr,'') NOT IN ('мейер','оба','не кц'))" % поля):
    inn, rus, napr, поч, ист, ts = р[:6]
    n = (р[6] if кн else "") or имя.get(str(inn), "")
    сайт = (р[-1] if кс else "") or ""
    дом = sorted(д for д in домены.get(str(inn), ()) if д not in ОБЩИЕ)
    сайт = re.sub(r"^https?://(www\.)?", "", str(сайт)).strip("/").lower() or (дом[0] if дом else "")
    вид = "ИНН" if re.fullmatch(r"\d{10}|\d{12}", str(inn)) else ("УНП" if re.fullmatch(r"\d{9}", str(inn)) else "ключ")
    строки.append([inn, вид, n, сайт, napr or "", rus or "", ист or "", (поч or "")[:200], (ts or "")[:10]])
    св[napr or rus] += 1
    св["вид: " + вид] += 1
строки.sort(key=lambda x: (x[4], x[2]))
имяф = "meyer-ne-pokupateli-%s.csv" % time.strftime("%m%d-%H%M")
путь = r"C:\sender\_ops" + "\\" + имяф
with io.open(путь, "w", encoding="utf-8-sig", newline="") as f:
    w = csv.writer(f, delimiter=";")
    w.writerow(["ИНН или ключ", "вид", "компания", "сайт/домен", "направление", "Руспром", "источник", "почему", "дата"])
    w.writerows(строки)
shutil.copy2(путь, r"C:\seostat\drop\drop-storage" + "\\" + имяф)
print("строк: %d; %s" % (len(строки), dict(св.most_common())))
print("файл: %s (и на дропе)" % имяф)
print("=== НЕ ПОКУПАТЕЛИ MEYER ===")
