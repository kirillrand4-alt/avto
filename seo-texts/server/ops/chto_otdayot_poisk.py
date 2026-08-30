# -*- coding: utf-8 -*-
"""Что реально отдаёт /v2/search: только счётчик или список с ИНН/ОГРН."""
import io
import json
import sys

import requests

КЛЮЧИ = r"C:\seostat\Parser2\data\api_keys.txt"
URL = "https://api.checko.ru/v2/search"
КОД = sys.argv[1] if len(sys.argv) > 1 else "10.61.3"
ключи = [с.strip().split()[0] for с in io.open(КЛЮЧИ, encoding="utf-8",
                                               errors="ignore")
         if с.strip() and not с.strip().startswith("#")]
s = requests.Session()
s.headers.update({"User-Agent": "Mozilla/5.0"})
for ключ in ключи[:25]:
    r = s.get(URL, params={"key": ключ, "by": "okved", "obj": "org",
                           "query": КОД, "active": "true", "page": 1},
              timeout=25)
    if r.status_code != 200:
        continue
    try:
        п = r.json()
    except Exception:                                              # noqa: BLE001
        continue
    if not isinstance(п, dict):
        continue
    блок = п.get("data", п)
    print("=== код %s ===" % КОД)
    print("ключи верхнего уровня: %s" % list(п.keys())[:10])
    if isinstance(блок, dict):
        print("ключи data: %s" % list(блок.keys())[:14])
        for имя in ("Записи", "data", "records", "items", "Результаты"):
            зап = блок.get(имя)
            if isinstance(зап, list):
                print("СПИСОК в поле %r: записей на странице %d" % (имя, len(зап)))
                if зап:
                    print("поля записи: %s" % list(зап[0].keys())[:16])
                    print("первая запись: %s"
                          % json.dumps(зап[0], ensure_ascii=False)[:400])
                break
        else:
            print("списка на верхнем уровне нет; сырой ответ: %s"
                  % json.dumps(п, ensure_ascii=False)[:500])
    else:
        print("data не словарь: %s" % json.dumps(п, ensure_ascii=False)[:400])
    break
else:
    print("ни один ключ не ответил")
