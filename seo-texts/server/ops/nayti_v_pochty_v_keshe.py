# -*- coding: utf-8 -*-
"""Искомый адрес во входном файле добора из кэша: с какой он страницы."""
import io
import json
import os
import re

ПОЧТА = "marushkiiin"
ФАЙЛЫ = [r"C:\sender\_tmp\pochty-v-keshe.jsonl"]
for кор in (r"C:\sender\_tmp", r"C:\sender\server", r"C:\seostat\drop"):
    if os.path.isdir(кор):
        for имя in os.listdir(кор):
            if re.search(r"pochty.*kesh|kesh.*pochty", имя, re.I):
                п = os.path.join(кор, имя)
                if п not in ФАЙЛЫ:
                    ФАЙЛЫ.append(п)

# шапка сборщика
for п in (r"C:\sender\server\pochty_iz_kesha_zapis.py",
          r"C:\sender\server\ops\pochty_iz_kesha_zapis.py"):
    if os.path.exists(п):
        т = io.open(п, encoding="utf-8", errors="replace").read()
        м = re.search(r'"""(.{0,1400}?)"""', т, re.S)
        print("=== ЧТО ДЕЛАЕТ pochty_iz_kesha_zapis.py ===")
        print(м.group(1).strip()[:1300] if м else "шапки нет")
        break

находки = []
осмотрено = []
for п in ФАЙЛЫ:
    if not os.path.exists(п):
        осмотрено.append("%s — НЕТ" % п)
        continue
    осмотрено.append("%s — %d Б" % (п, os.path.getsize(п)))
    for с in io.open(п, encoding="utf-8", errors="replace"):
        if ПОЧТА in с:
            try:
                z = json.loads(с)
                находки.append((os.path.basename(п),
                                json.dumps(z, ensure_ascii=False)[:700]))
            except Exception:                                  # noqa: BLE001
                находки.append((os.path.basename(п), с.strip()[:700]))
            if len(находки) >= 5:
                break

print("")
print("=" * 84)
print("=== СВОДКА: ГДЕ НАШЁЛСЯ АДРЕС ВО ВХОДЕ ДОБОРА ===")
print("осмотренные файлы:")
for с in осмотрено:
    print("   " + с)
print("")
if находки:
    for имя, з in находки:
        print("   --- %s ---" % имя)
        print("   " + з)
        print("")
else:
    print("   во входных файлах добора адрес не найден")
