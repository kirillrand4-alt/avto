# -*- coding: utf-8 -*-
"""Чистка вердиктов «Meyer — не покупатель» по разбору 13.10 и новая выгрузка.

Что считаем браком вердикта:
  * старое «не мейер» — отсев предкласса генератора по старым правилам, без
    причины; при слиянии часть ушла под ярлык гейта/линзы (гейт дописал только
    «покупатель Руспрома», а направление осталось чужое);
  * критика письма вместо компании («обещать небезопасно», «приписано»);
  * причина противоречит итогу («прямой кандидат на фотосепаратор» → не Meyer);
  * сайт не подтверждён (verified = mismatch / спорно) — судили по однофамильцу.
Старое «не мейер» заменяем решением предкласса 13.10 (новые правила), если оно
есть, иначе стираем направление. Бракованные причины — стираем направление.
Резерв затронутых строк — _ops/chistka-ne-meyer-bak.jsonl (fsync) до записи.

Выгрузка: A — решение с причиной про компанию (гейт, линза, реестр);
          B — предклассификатор по паспорту по правилам 13.10 (без текста причины).

    chistka_ne_meyer.py [--primenit]
"""
import csv
import io
import json
import os
import re
import shutil
import sqlite3
import sys
import time
from collections import Counter, defaultdict
ПРИМ = "--primenit" in sys.argv
ПИСЬМО = re.compile(r"письм|обеща|небезопасн|формулир|в тексте|приписан|сказано то, чего нет|нельзя писать|силикон|не находит", re.I)
ПРОТИВ = re.compile(r"прямой кандидат|(?<![а-я])кандидат на фото|покупатель рентгена|подходит Meyer|— покупател", re.I)
ПЛОХОЙ_САЙТ = {"mismatch", "спорно"}
пк = {}
for с in io.open(r"C:\sender\_ops\predklass-vsey-bazy.jsonl", encoding="utf-8"):
    з = json.loads(с)
    пк[з["inn"]] = з["napr"]
e = sqlite3.connect(r"C:\sender\enrich.db", timeout=60)
o = sqlite3.connect(r"C:\sender\obzvon-index.db", timeout=60)
s = sqlite3.connect(r"C:\sender\sender.db", timeout=30)
домены = defaultdict(set)
for inn, em in s.execute("SELECT inn, email FROM recipients WHERE inn IS NOT NULL AND email LIKE '%@%'"):
    домены[str(inn)].add(em.split("@")[1].lower())
ОБЩИЕ = {"mail.ru", "yandex.ru", "ya.ru", "gmail.com", "inbox.ru", "list.ru", "bk.ru", "rambler.ru", "yandex.by",
         "mail.by", "tut.by", "icloud.com", "outlook.com", "hotmail.com"}
св, правки, A, B = Counter(), [], [], []
for inn, name, napr, rus, ист, поч, ver, site in e.execute(
        "SELECT inn, name, verdikt_napr, verdikt_rusprom, verdikt_istochnik, verdikt_pochemu, verified, site "
        "FROM companies WHERE verdikt_napr IS NOT NULL OR verdikt_rusprom IS NOT NULL"):
    поч = поч or ""
    нов_napr = napr
    if napr == "не мейер" and (ист == "предкласс" or rus == "покупатель" or "другое направление" in поч):
        нов_napr = пк.get(inn)        # старый ярлык → решение 13.10 или пусто
        св["старое «не мейер» → %s" % (нов_napr or "пусто")] += 1
    elif napr in ("не мейер", "кц") and ист == "линза" and ПИСЬМО.search(поч):
        нов_napr = None
        св["критика письма → пусто"] += 1
    if нов_napr in ("кц", "никуда", "не мейер") and ПРОТИВ.search(поч) and ист != "предкласс":
        нов_napr = None
        св["противоречие → пусто"] += 1
    нов_rus = rus
    if rus == "не покупатель" and ист == "линза" and ПИСЬМО.search(поч):
        нов_rus = None
    if (нов_napr, нов_rus) != (napr, rus):
        правки.append({"inn": inn, "было": [napr, rus, ист, поч], "стало": [нов_napr, нов_rus]})
    плохой_сайт = (ver or "") in ПЛОХОЙ_САЙТ
    не_мейер = нов_napr in ("кц", "никуда", "не мейер") or (нов_rus == "не покупатель" and нов_napr not in ("мейер", "оба", "не кц"))
    if not не_мейер:
        continue
    if плохой_сайт:
        св["в выгрузку не взят: сайт не подтверждён"] += 1
        continue
    сайт = re.sub(r"^https?://(www\.)?", "", str(site or "")).strip("/").lower() or \
        next(iter(sorted(д for д in домены.get(str(inn), ()) if д not in ОБЩИЕ)), "")
    вид = "ИНН" if re.fullmatch(r"\d{10}|\d{12}", str(inn)) else ("УНП" if re.fullmatch(r"\d{9}", str(inn)) else "ключ")
    строка = [inn, вид, name or "", сайт, нов_napr or "", нов_rus or "", ист or "", поч[:200]]
    if ист == "предкласс" or нов_napr != napr:
        строка[6] = "предкласс 13.10"
        строка[7] = "по паспорту сайта, правила владельца 13.10"
        B.append(строка)
    else:
        A.append(строка)
print("правок вердиктов: %d" % len(правки))
for к, n in св.most_common():
    print("   %-45s %d" % (к, n))
print("выгрузка A (с причиной): %d; B (предкласс по паспорту): %d" % (len(A), len(B)))
print("A по источникам: %s" % dict(Counter(x[6] for x in A)))
if ПРИМ and правки:
    with io.open(r"C:\sender\_ops\chistka-ne-meyer-bak.jsonl", "a", encoding="utf-8") as ж:
        for п in правки:
            ж.write(json.dumps(п, ensure_ascii=False) + "\n")
        ж.flush()
        os.fsync(ж.fileno())
    ts = time.strftime("%Y-%m-%dT%H:%M:%S")
    for п in правки:
        n, r = п["стало"]
        поч = п["было"][3]
        ист = п["было"][2]
        if n != п["было"][0] and n in ("кц", "никуда", "мейер", "оба") and п["было"][0] == "не мейер":
            поч, ист = "предклассификатор по паспорту (вся база 13.10)", "предкласс"
        e.execute("UPDATE companies SET verdikt_napr=?, verdikt_rusprom=?, verdikt_pochemu=?, verdikt_istochnik=?, "
                  "verdikt_ts=? WHERE inn=?", (n, r, поч, ист, ts, п["inn"]))
        o.execute("INSERT INTO kompaniya_verdikt (inn, rusprom, napr, pochemu, istochnik, ts) VALUES (?,?,?,?,?,?) "
                  "ON CONFLICT(inn) DO UPDATE SET rusprom=excluded.rusprom, napr=excluded.napr, "
                  "pochemu=excluded.pochemu, istochnik=excluded.istochnik, ts=excluded.ts", (п["inn"], r, n, поч, ист, ts))
    e.commit()
    o.commit()
    print("применено в enrich + obzvon")
метка = time.strftime("%m%d-%H%M")
for буква, строки in (("A-s-prichinoy", A), ("B-predklass", B)):
    имяф = "meyer-ne-pokupateli-%s-%s.csv" % (буква, метка)
    путь = r"C:\sender\_ops" + "\\" + имяф
    with io.open(путь, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["ИНН или ключ", "вид", "компания", "сайт/домен", "направление", "Руспром", "источник", "почему"])
        w.writerows(sorted(строки, key=lambda x: (x[4], x[2])))
    shutil.copy2(путь, r"C:\seostat\drop\drop-storage" + "\\" + имяф)
    print("файл: %s" % имяф)
print("=== ЧИСТКА НЕ МЕЙЕР: %s ===" % ("ПРИМЕНЕНО" if ПРИМ else "сухой прогон"))
