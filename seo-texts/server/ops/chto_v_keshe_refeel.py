# -*- coding: utf-8 -*-
"""Какие страницы refeel.ru сохранены и где вообще встречается адрес.

Ищем ПО ВСЕМ кэшам и рабочим файлам, а не только по этой компании: метка
source='own-site' могла быть проставлена по ошибке, и тогда настоящий
источник найдётся в другом месте.
"""
import glob
import gzip
import io
import json
import os
import re

ПОЧТА = "marushkiiin"
ИНН = "7842186599"
КЭШ = r"C:\seostat\drop\pagecache"

# 1) что сохранено по этой компании
п = os.path.join(КЭШ, "%s.json.gz" % ИНН)
урлы = []
есть_почта_в_файле = False
if os.path.exists(п):
    сырое = gzip.open(п, "rt", encoding="utf-8", errors="replace").read()
    есть_почта_в_файле = ПОЧТА in сырое
    try:
        д = json.loads(сырое)
        if isinstance(д, dict):
            урлы = list(д.keys())
        elif isinstance(д, list):
            урлы = [str(э.get("url") or "?") for э in д
                    if isinstance(э, dict)]
    except Exception as ex:                                    # noqa: BLE001
        урлы = ["(json не разобрался: %s)" % str(ex)[:50]]

# 2) где ещё встречается адрес — по кэшам и рабочим файлам
где_ещё = []
корни = [КЭШ, r"C:\seostat\drop\zenno\razobrano", r"C:\seostat\drop",
         r"C:\sender\server", r"C:\sender\_ops"]
просмотрено = 0
for корень in корни:
    if not os.path.isdir(корень):
        continue
    for путь, кат, файлы in os.walk(корень):
        кат[:] = [d for d in кат if d not in ("__pycache__", ".git", ".venv")]
        for имя in файлы:
            ф = os.path.join(путь, имя)
            try:
                рз = os.path.getsize(ф)
            except Exception:                                  # noqa: BLE001
                continue
            if рз > 8_000_000:
                continue
            if not имя.endswith((".gz", ".json", ".jsonl", ".txt", ".csv",
                                 ".html")):
                continue
            просмотрено += 1
            try:
                т = (gzip.open(ф, "rt", encoding="utf-8", errors="replace").read()
                     if имя.endswith(".gz") else
                     io.open(ф, encoding="utf-8", errors="replace").read())
            except Exception:                                  # noqa: BLE001
                continue
            if ПОЧТА in т:
                i = т.find(ПОЧТА)
                кусок = re.sub(r"\s+", " ",
                               re.sub(r"<[^>]+>", " ",
                                      т[max(0, i - 200):i + 200]))
                где_ещё.append((ф.replace("C:\\", ""), кусок.strip()[:220]))
            if len(где_ещё) > 12 or просмотрено > 60000:
                break
        if len(где_ещё) > 12 or просмотрено > 60000:
            break
    if len(где_ещё) > 12:
        break

print("=" * 84)
print("=== СВОДКА: ГДЕ ВСТРЕЧАЕТСЯ АДРЕС ===")
print("файл кэша по компании: %s" % ("есть" if os.path.exists(п) else "НЕТ"))
print("адрес внутри этого файла: %s"
      % ("ЕСТЬ" if есть_почта_в_файле else "нет"))
print("")
print("сохранённые страницы refeel.ru (%d):" % len(урлы))
for у in урлы[:25]:
    print("   %s" % str(у)[:120])
print("")
print("просмотрено файлов: %d" % просмотрено)
print("найден адрес в %d местах:" % len(где_ещё))
for ф, кусок in где_ещё[:12]:
    print("")
    print("   %s" % ф[:110])
    print("      ...%s..." % кусок)
