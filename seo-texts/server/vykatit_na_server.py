# -*- coding: utf-8 -*-
"""Залить скрипты на сервер БЕЗ запуска.

`zapusk_svoego_skripta.py` заливает и тут же запускает - для отчётов это
удобно, но выкатка и запуск это разные действия. Скрипт-убийцу лишних
прогонов и счётчик прогонов надо иметь на сервере ЗАРАНЕЕ, ещё до того как
понадобится их звать; генератор - заливать при нуле прогонов, а запускать
отдельным решением. Питон читает файл при старте процесса, поэтому правка,
залитая поверх работающего круга, не выполнится ни разу (грабли 17.08).

    python3 vykatit_na_server.py ops/partiya_gen.py ops/partiya_hod.py
"""
import base64
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import run_on_server as R  # noqa: E402

пути = sys.argv[1:]
if not пути:
    print("нечего заливать: укажи файлы", file=sys.stderr)
    raise SystemExit(2)

файлы = []
for p in пути:
    b = open(p, "rb").read()
    dest = r"C:\sender\_ops" + "\\" + os.path.basename(p)
    файлы.append({"b64": base64.b64encode(b).decode(), "dest": dest})
    print(f"{p} -> {dest} ({len(b)} байт)")

res = R.submit("enrich_contacts", {"op": "panel_file_put", "files": файлы},
               wait=True, poll=8, timeout=300)
d = (res or {}).get("data") or {}
print("ответ сервера:", d or res)
print("залито файлов:", len(файлы))
