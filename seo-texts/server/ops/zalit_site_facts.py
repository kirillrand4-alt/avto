# -*- coding: utf-8 -*-
"""Залить структурный паспорт сайта из книг в enrich.db/site_facts.

Генератор письма берёт паспорт ИМЕННО отсюда: по нему подбирается продукт
каталога (а значит ролик и беды культуры из таблицы владельца), и только
при «оборудование_линии» письму разрешено называть цеха. Плоский
companies.activity этого не заменяет.

Правило слияния: по каждому ключу берём БОЛЕЕ ПОЛНЫЙ список (книга или то,
что уже собрал обходчик) — ничего не теряем. Прочие ключи обходчика
(клиенты, новости, разбор_КЦ…) не трогаем. Журнал с fsync.

Запуск: zalit_site_facts.py [--primenit]
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
ЖУРНАЛ = r"C:\sender\_ops\site-facts-knigi.jsonl"
КЛЮЧИ = ("продукция", "сырьё", "мощности", "контроль_качества",
         "оборудование_линии", "упаковка_фасовка", "экспорт", "масштаб")
ПУСТОЙ = {"продукция": [], "упаковка_фасовка": [], "сырьё": [], "мощности": [],
          "контроль_качества": [], "экспорт": [], "оборудование_линии": [],
          "клиенты": [], "год_основания": "", "география_поставок": [],
          "масштаб": [], "энергохозяйство": [], "расширение": [], "газы": [],
          "новости": [], "свежая_новость": "", "цитата": "", "источники": [],
          "уверенность": ""}

записи = []
for п in sorted(glob.glob(r"C:\sender\server\ops\pasp2_*.json")):
    записи.extend(json.load(io.open(п, encoding="utf-8")))
print("паспортов из книг: %d" % len(записи))

cx = sqlite3.connect(r"C:\sender\enrich.db", timeout=60)
cx.row_factory = sqlite3.Row
свод = Counter()
ключей_добавлено = Counter()
ж = io.open(ЖУРНАЛ, "a", encoding="utf-8") if ПРИМЕНИТЬ else None
ts = time.strftime("%Y-%m-%dT%H:%M:%S")
for з in записи:
    инн = з["inn"]
    р = cx.execute("SELECT facts_json, sources_json FROM site_facts WHERE inn=?",
                   (инн,)).fetchone()
    было = {}
    if р is not None:
        try:
            было = json.loads(р["facts_json"] or "{}") or {}
        except Exception:  # noqa: BLE001
            было = {}
    новое = dict(ПУСТОЙ)
    новое.update(было if isinstance(было, dict) else {})
    изм = []
    for к in КЛЮЧИ:
        книга = [x for x in (з["f"].get(к) or []) if x]
        стар = [x for x in (новое.get(к) or []) if x] if isinstance(
            новое.get(к), list) else []
        if len(книга) > len(стар):
            новое[к] = книга
            изм.append(к)
    источники = list(новое.get("источники") or [])
    if з.get("url") and з["url"] not in источники:
        источники.append(з["url"])
    новое["источники"] = источники
    if not новое.get("уверенность"):
        новое["уверенность"] = "средняя" if з.get("lvl2") else "высокая"
    if р is None:
        свод["паспорт заведён"] += 1
    elif изм:
        свод["паспорт дополнен"] += 1
    else:
        свод["у обходчика было не хуже"] += 1
        continue
    for к in изм:
        ключей_добавлено[к] += 1
    if not ПРИМЕНИТЬ:
        continue
    фj = json.dumps(новое, ensure_ascii=False)
    иj = json.dumps(источники, ensure_ascii=False)
    if р is None:
        cx.execute("INSERT INTO site_facts (inn, facts_json, sources_json, site,"
                   " ts, note) VALUES (?,?,?,?,?,?)",
                   (инн, фj, иj, з.get("site") or "", ts, "knigi-meyer7"))
    else:
        cx.execute("UPDATE site_facts SET facts_json=?, sources_json=?, ts=?,"
                   " note=COALESCE(note,'')||' +knigi-meyer7' WHERE inn=?",
                   (фj, иj, ts, инн))
    ж.write(json.dumps({"inn": инн, "ключи": изм, "новый": р is None},
                       ensure_ascii=False) + "\n")
if ПРИМЕНИТЬ:
    cx.commit()
    ж.flush()
    os.fsync(ж.fileno())
    ж.close()
cx.close()

print("")
for к, n in свод.most_common():
    print("   %-30s %6d" % (к, n))
print("")
print("--- какие разделы паспорта книга добавила/расширила ---")
for к, n in ключей_добавлено.most_common():
    print("   %-24s %6d" % (к, n))
print("")
print("=== СТРУКТУРНЫЙ ПАСПОРТ В SITE_FACTS ===")
print("   режим: %s" % ("ПРИМЕНЕНО" if ПРИМЕНИТЬ else "сухой прогон"))
print("   заведено %d, дополнено %d, не хуже было %d"
      % (свод["паспорт заведён"], свод["паспорт дополнен"],
         свод["у обходчика было не хуже"]))
