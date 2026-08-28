# -*- coding: utf-8 -*-
"""Пересланный ответ не должен обрезаться на шапке пересылки (lid_ssylka.py).

bez_citaty резала всё от первой строки «Кому:/Дата:/Тема:» до конца — верно для
ответа с цитатой снизу и неверно для ПЕРЕСЫЛКИ, где ниже шапки лежит письмо
человека. По «Импэкс-Дону» так пропала подпись главного механика с мобильным."""
import io
import json
import os
import py_compile
import time

ПУТЬ = r"C:\sender\sender\lid_ssylka.py"
ЗАМЕНЫ = json.loads(r'''[["    r'-{4,}\\s*'\n    r')\\s*$', re.I)\n", "    r'-{4,}\\s*'\n    r')\\s*$', re.I)\n\n# ПЕРЕСЫЛКА — не цитата: под её шапкой лежит письмо ЧЕЛОВЕКА, а не наше.\n_ШАПКА_ПЕРЕСЫЛКИ = re.compile(\n    r'^\\s*(?:>\\s*)*(?:-{2,}\\s*)?'\n    r'(?:Пересыла\\w+\\s+сообщени\\w+|Пересланное\\s+сообщени\\w+|'\n    r'Forwarded\\s+message|Begin\\s+forwarded\\s+message)'\n    r'\\s*(?:-{2,})?\\s*:?\\s*$', re.I)\n"], ["    for i, с in enumerate(строки):\n        if not _ШАПКА_ЦИТАТЫ.match(с):\n            continue\n        выше = '\\n'.join(строки[:i]).strip()\n        if len(re.sub(r'\\s+', ' ', выше)) >= 40:\n            строки = строки[:i]\n            break\n", "    # ПЕРЕСЫЛКА ЛОМАЕТ ЭТО ПРАВИЛО. Секретарь пересылает нам ответ\n    # ответственного, и слова человека лежат НИЖЕ шапки «От кого / Кому / Дата\n    # / Тема» — резать от первой шапки до конца там нельзя. 28.08 по\n    # «Импэкс-Дону» так пропала подпись главного механика с его мобильным:\n    # ровно то, ради чего продажник страницу и открывает. Ниже шапки пересылки\n    # цитату добирают знаки «>», а нашу подпись — bez_nashey_podpisi.\n    переслано = next((k for k, л in enumerate(строки)\n                      if _ШАПКА_ПЕРЕСЫЛКИ.match(л)), None)\n    for i, с in enumerate(строки):\n        if переслано is not None and i > переслано:\n            break\n        if not _ШАПКА_ЦИТАТЫ.match(с):\n            continue\n        выше = '\\n'.join(строки[:i]).strip()\n        if len(re.sub(r'\\s+', ' ', выше)) >= 40:\n            строки = строки[:i]\n            break\n"]]''')

т = io.open(ПУТЬ, encoding="utf-8").read()
if "_ШАПКА_ПЕРЕСЫЛКИ" in т:
    print("правка уже стоит")
    raise SystemExit(0)
for стар, нов in ЗАМЕНЫ:
    if т.count(стар) != 1:
        print("ЯКОРЬ НЕ ОДИН (%d): %r" % (т.count(стар), стар[:70]))
        raise SystemExit(1)
было = т
for стар, нов in ЗАМЕНЫ:
    т = т.replace(стар, нов)
бэк = ПУТЬ + ".bak-%d" % int(time.time())
with io.open(бэк, "w", encoding="utf-8", newline="") as f:
    f.write(было); f.flush(); os.fsync(f.fileno())
with io.open(ПУТЬ, "w", encoding="utf-8", newline="") as f:
    f.write(т); f.flush(); os.fsync(f.fileno())
try:
    py_compile.compile(ПУТЬ, doraise=True)
except Exception as ex:
    with io.open(ПУТЬ, "w", encoding="utf-8", newline="") as f:
        f.write(было); f.flush(); os.fsync(f.fileno())
    print("НЕ КОМПИЛИРУЕТСЯ, откатил: %s" % ex)
    raise SystemExit(1)
print("готово: %d -> %d знаков, бэкап %s" % (len(было), len(т), os.path.basename(бэк)))
