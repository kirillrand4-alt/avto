# -*- coding: utf-8 -*-
"""Идёт ли прогон партии прямо сейчас: растёт ли журнал, что в хвосте."""
import io
import json
import os
import time

ЖУРНАЛ = r"C:\sender\_ops\gen-partiya-935.jsonl"
st = os.stat(ЖУРНАЛ)
print(f"журнал: {st.st_size} байт, изменён {int(time.time() - st.st_mtime)} с назад")
хвост = []
for s in io.open(ЖУРНАЛ, encoding="utf-8"):
    хвост.append(s)
хвост = хвост[-12:]
for s in хвост:
    try:
        z = json.loads(s)
    except Exception:                                        # noqa: BLE001
        continue
    print(f"  [{str(z.get('этап') or '—'):<18}] ок={z.get('ок')} "
          f"{str(z.get('имя') or z.get('inn'))[:34]:<34} "
          f"${z.get('цена_$')} {str(z.get('модель') or '')}")
# Кто ещё жив: питоны панели с partiya_gen в командной строке.
try:
    import subprocess
    out = subprocess.run(
        ["wmic", "process", "where", "name='python.exe'", "get",
         "ProcessId,CommandLine"], capture_output=True, text=True, timeout=60)
    for с in (out.stdout or "").splitlines():
        if "partiya_gen" in с:
            print("живой процесс:", с.strip()[:160])
except Exception as ex:                                      # noqa: BLE001
    print("процессы не спросить:", str(ex)[:80])
