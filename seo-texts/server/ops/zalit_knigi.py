# -*- coding: utf-8 -*-
"""Залить книги паспортов в обогащение: компании, паспорт, адреса.

Владелец 12.10 утвердил: паспорт утверждаем всем (включая холдинги),
классы сомнения А и Б — первый уровень, В/Г/Д — второй (verified пустой).
Пишем ТОЛЬКО в серверное durable-хранилище (enrich.db) + зеркало в jsonl
с fsync, чтобы рестарт песочницы ничего не унёс.

Запуск: zalit_knigi.py [--primenit]   (без флага — сухой прогон).
"""
import glob
import io
import json
import os
import sqlite3
import sys
import time
from collections import Counter

ПРИМЕНИТЬ = "--primenit" in sys.argv
БД = r"C:\sender\enrich.db"
ЖУРНАЛ = r"C:\sender\_ops\knigi-zaliv.jsonl"

компании, адреса = [], []
for п in sorted(glob.glob(r"C:\sender\server\ops\knigi2_*.json")):
    д = json.load(io.open(п, encoding="utf-8"))
    компании.extend(д.get("компании") or [])
    адреса.extend(д.get("адреса") or [])
print("кусков прочитано: %d, компаний %d, адресов %d"
      % (len(glob.glob(r"C:\sender\server\ops\knigi2_*.json")),
         len(компании), len(адреса)))
if not компании:
    print("КУСКОВ НЕТ — выходим")
    sys.exit(0)

cx = sqlite3.connect(БД, timeout=60)
cx.row_factory = sqlite3.Row
колонки = {р["name"] for р in cx.execute("PRAGMA table_info(companies)")}
кол_адр = {р["name"] for р in cx.execute("PRAGMA table_info(emails)")}
print("companies: %s" % ", ".join(sorted(колонки)))
print("emails:    %s" % ", ".join(sorted(кол_адр)))

ПОЛЯ = [("name", "name"), ("site", "site"), ("activity", "activity"),
        ("verified", "site_verified"), ("region", "region"),
        ("okved", "okved"), ("okved_all", "okved_all"),
        ("revenue", "revenue")]
ПОЛЯ = [(к, с) for к, с in ПОЛЯ if с in колонки]
print("пишем колонки: %s" % ", ".join(с for _, с in ПОЛЯ))

свод = Counter()
журнал = io.open(ЖУРНАЛ, "a", encoding="utf-8") if ПРИМЕНИТЬ else None
ts = int(time.time())
for к in компании:
    инн = к["inn"]
    было = cx.execute("SELECT * FROM companies WHERE inn=?", (инн,)).fetchone()
    нов = {}
    for ключ, стлб in ПОЛЯ:
        з = к.get(ключ)
        if з in (None, ""):
            continue
        стар = (было[стлб] if было is not None and стлб in было.keys() else None)
        # паспорт не затираем более коротким, остальное обновляем
        if стлб == "activity" and стар and len(str(стар)) >= len(str(з)):
            continue
        if стар == з:
            continue
        нов[стлб] = з
    if было is None:
        свод["компаний заведено"] += 1
    elif нов:
        свод["компаний обновлено"] += 1
    else:
        свод["компаний без изменений"] += 1
        continue
    if not ПРИМЕНИТЬ:
        continue
    if было is None:
        поля = ["inn"] + list(нов)
        cx.execute("INSERT INTO companies (%s) VALUES (%s)"
                   % (",".join(поля), ",".join("?" * len(поля))),
                   [инн] + [нов[п] for п in нов])
    else:
        cx.execute("UPDATE companies SET %s WHERE inn=?"
                   % ",".join("%s=?" % п for п in нов),
                   [нов[п] for п in нов] + [инн])
    журнал.write(json.dumps({"ts": ts, "что": "company", "inn": инн,
                             "поля": нов}, ensure_ascii=False) + "\n")

ЕСТЬ_РОЛЬ = "role" in кол_адр
ЕСТЬ_ИСТ = "source" in кол_адр
ЕСТЬ_URL = "source_url" in кол_адр
for а in адреса:
    инн, почта = а["inn"], а["email"]
    было = cx.execute("SELECT * FROM emails WHERE inn=? AND email=?",
                      (инн, почта)).fetchone()
    if было is not None:
        свод["адресов уже было"] += 1
        if ПРИМЕНИТЬ and ЕСТЬ_РОЛЬ and а.get("role") and not (
                было["role"] if "role" in было.keys() else ""):
            cx.execute("UPDATE emails SET role=? WHERE inn=? AND email=?",
                       (а["role"][:120], инн, почта))
            свод["адресам проставлена роль"] += 1
        continue
    свод["адресов заведено"] += 1
    if not ПРИМЕНИТЬ:
        continue
    поля, зн = ["inn", "email"], [инн, почта]
    if ЕСТЬ_РОЛЬ:
        поля.append("role"), зн.append(str(а.get("role") or "")[:120])
    if ЕСТЬ_ИСТ:
        поля.append("source"), зн.append("knigi-meyer7")
    if ЕСТЬ_URL:
        поля.append("source_url"), зн.append(str(а.get("url") or "")[:300])
    cx.execute("INSERT INTO emails (%s) VALUES (%s)"
               % (",".join(поля), ",".join("?" * len(поля))), зн)
    журнал.write(json.dumps({"ts": ts, "что": "email", "inn": инн,
                             "email": почта,
                             "role": а.get("role")}, ensure_ascii=False) + "\n")

if ПРИМЕНИТЬ:
    cx.commit()
    журнал.flush()
    os.fsync(журнал.fileno())
    журнал.close()
cx.close()

print("")
for кл, n in свод.most_common():
    print("   %-34s %6d" % (кл, n))
print("")
print("=" * 70)
print("=== ЗАЛИВКА КНИГ В ОБОГАЩЕНИЕ ===")
print("   режим:                 %s" % ("ПРИМЕНЕНО" if ПРИМЕНИТЬ else "сухой прогон"))
print("   компаний заведено:     %6d" % свод.get("компаний заведено", 0))
print("   компаний обновлено:    %6d" % свод.get("компаний обновлено", 0))
print("   адресов заведено:      %6d" % свод.get("адресов заведено", 0))
print("   журнал:                %s" % ЖУРНАЛ)
