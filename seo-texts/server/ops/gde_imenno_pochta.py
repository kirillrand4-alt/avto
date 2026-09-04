# -*- coding: utf-8 -*-
"""На какой именно странице refeel.ru лежит marushkiiin@yandex.ru.

Обойдённые страницы хранятся в кэше C:\\seostat\\drop\\pagecache\\<ИНН>.json.gz —
ищем адрес прямо в них и печатаем URL и окружающий текст.
"""
import glob
import gzip
import json
import os
import re

ПОЧТА = "marushkiiin@yandex.ru"
ИНН = "7842186599"
КЭШ = r"C:\seostat\drop\pagecache"

файлы = []
for шаблон in ("%s.json.gz" % ИНН, "%s*.json*" % ИНН):
    файлы.extend(glob.glob(os.path.join(КЭШ, шаблон)))
файлы = sorted(set(файлы))

print("=== ФАЙЛЫ КЭША ПО ИНН %s ===" % ИНН)
for п in файлы:
    print("   %s  %d Б" % (os.path.basename(п), os.path.getsize(п)))
if not файлы:
    print("   ничего не найдено в %s" % КЭШ)

находки = []
for п in файлы:
    try:
        сырое = (gzip.open(п, "rt", encoding="utf-8", errors="replace").read()
                 if п.endswith(".gz") else
                 open(п, encoding="utf-8", errors="replace").read())
    except Exception as ex:                                    # noqa: BLE001
        print("   %s не прочитался: %s" % (os.path.basename(п), str(ex)[:60]))
        continue
    try:
        д = json.loads(сырое)
    except Exception:                                          # noqa: BLE001
        д = None
    страницы = []
    if isinstance(д, dict):
        for к, v in д.items():
            if isinstance(v, str):
                страницы.append((к, v))
            elif isinstance(v, dict):
                for к2, v2 in v.items():
                    if isinstance(v2, str):
                        страницы.append(("%s/%s" % (к, к2), v2))
    elif isinstance(д, list):
        for э in д:
            if isinstance(э, dict):
                страницы.append((str(э.get("url") or э.get("адрес") or "?"),
                                 str(э.get("html") or э.get("text") or "")))
    else:
        страницы.append((os.path.basename(п), сырое))

    for урл, тело in страницы:
        if ПОЧТА in тело:
            i = тело.find(ПОЧТА)
            кусок = re.sub(r"<[^>]+>", " ", тело[max(0, i - 400):i + 300])
            кусок = re.sub(r"\s+", " ", кусок).strip()
            находки.append((урл, кусок))

print("")
print("=" * 84)
print("=== СВОДКА: ГДЕ ИМЕННО ЛЕЖИТ %s ===" % ПОЧТА)
if находки:
    for урл, кусок in находки[:6]:
        print("")
        print("   СТРАНИЦА: %s" % урл[:120])
        print("   ...%s..." % кусок[:600])
else:
    print("   в кэше страниц этот адрес НЕ НАЙДЕН")
    print("   значит он попал в базу не из сохранённых страниц —")
    print("   пометка «кэш-добор» указывает на добор из кэша обхода,")
    print("   но самой страницы с ним в кэше уже нет")
