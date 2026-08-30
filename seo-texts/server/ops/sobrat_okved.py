# -*- coding: utf-8 -*-
"""Собрать компании по кодам ОКВЭД из api.checko.ru/v2/search в журнал.

Эндпоинт отдаёт не только счётчик: в data.Записи лежат ОГРН, ИНН, КПП,
НаимСокр/НаимПолн, ДатаРег, Статус, РегионКод, ЮрАдрес, ОКВЭД, Руковод,
Учред — по 100 на страницу, всего страниц в data.СтрВсего.

DURABILITY: пишем в журнал с fsync, базу в горячем пути не трогаем (enrich.db
надолго берут соседние службы). Прогон резюмируемый: по журналу знаем, какие
страницы каких кодов уже взяты.

Ключи: пул Parser2/data/api_keys.txt с ротацией — у каждого суточный лимит.
Ключ, ответивший без данных, откладываем и берём следующий.

Запуск: python sobrat_okved.py [бюджет_сек] [код ...]
"""
import io
import json
import os
import sys
import time

import requests

КЛЮЧИ_ФАЙЛ = r"C:\seostat\Parser2\data\api_keys.txt"
ЖУРНАЛ = r"C:\sender\_ops\okved-pool.jsonl"
ПРОГРЕСС = r"C:\sender\_ops\okved-pool-progress.json"
URL = "https://api.checko.ru/v2/search"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131"

БЮДЖЕТ = float(sys.argv[1]) if len(sys.argv) > 1 else 600.0
КОДЫ = sys.argv[2:] or ["10.61.3", "10.61.2"]

ключи = [с.strip().split()[0] for с in io.open(КЛЮЧИ_ФАЙЛ, encoding="utf-8",
                                               errors="ignore")
         if с.strip() and not с.strip().startswith("#")]
_поз = [0]


def взять_ключ():
    к = ключи[_поз[0] % len(ключи)]
    _поз[0] += 1
    return к


прогресс = {}
if os.path.exists(ПРОГРЕСС):
    try:
        прогресс = json.load(io.open(ПРОГРЕСС, encoding="utf-8"))
    except Exception:                                              # noqa: BLE001
        прогресс = {}

s = requests.Session()
s.headers.update({"User-Agent": UA})
ж = io.open(ЖУРНАЛ, "a", encoding="utf-8")
t0 = time.time()
всего_записей = запросов = пустых = 0
итоги = {}
try:
    for код in КОДЫ:
        сдел = int(прогресс.get(код, {}).get("страниц", 0))
        стр_всего = int(прогресс.get(код, {}).get("всего_страниц", 0)) or None
        собрано = int(прогресс.get(код, {}).get("записей", 0))
        стр = сдел + 1
        while time.time() - t0 < БЮДЖЕТ:
            данные = None
            for _ in range(12):                    # ротация ключей
                if time.time() - t0 > БЮДЖЕТ:
                    break
                ключ = взять_ключ()
                запросов += 1
                try:
                    r = s.get(URL, params={"key": ключ, "by": "okved",
                                           "obj": "org", "query": код,
                                           "active": "true", "page": стр},
                              timeout=30)
                except Exception:                                  # noqa: BLE001
                    continue
                if r.status_code != 200:
                    continue
                try:
                    п = r.json()
                except Exception:                                  # noqa: BLE001
                    continue
                б = п.get("data") if isinstance(п, dict) else None
                if isinstance(б, dict) and isinstance(б.get("Записи"), list):
                    данные = б
                    break
                пустых += 1
            if данные is None:
                print("   %s: страница %d не далась (ключи молчат)" % (код, стр))
                break
            стр_всего = int(данные.get("СтрВсего") or 0) or стр_всего
            записи = данные.get("Записи") or []
            for з in записи:
                з["_okved_zapros"] = код
                ж.write(json.dumps(з, ensure_ascii=False) + "\n")
            собрано += len(записи)
            всего_записей += len(записи)
            ж.flush()
            os.fsync(ж.fileno())
            прогресс[код] = {"страниц": стр, "всего_страниц": стр_всего,
                             "записей": собрано,
                             "всего_записей": данные.get("ЗапВсего")}
            with io.open(ПРОГРЕСС, "w", encoding="utf-8") as f:
                json.dump(прогресс, f, ensure_ascii=False)
                f.flush()
                os.fsync(f.fileno())
            if not записи or (стр_всего and стр >= стр_всего):
                break
            стр += 1
        итоги[код] = прогресс.get(код, {})
finally:
    ж.flush()
    os.fsync(ж.fileno())
    ж.close()

строк = sum(1 for _ in io.open(ЖУРНАЛ, encoding="utf-8", errors="ignore"))
print(json.dumps({"собрано_за_прогон": всего_записей, "запросов": запросов,
                  "пустых_ответов": пустых, "строк_в_журнале": строк,
                  "секунд": round(time.time() - t0, 1), "по_кодам": итоги},
                 ensure_ascii=False)[:1200])
