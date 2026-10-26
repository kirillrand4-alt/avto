# -*- coding: utf-8 -*-
"""Снимок стеков потоков службы SenderPanel через py-spy dump (процесс не
останавливается). Ищем, на какой строке висит проход автоотправки. Пишет
_ops/stek-sluzhby-<время>.txt и на дроп stek-sluzhby.txt. Только чтение."""
import os
import subprocess
import time

import requests

вывод = subprocess.run(["wmic", "process", "where", "name like 'python%'", "get", "ProcessId,CommandLine", "/format:list"],
                       capture_output=True, text=True, errors="replace").stdout
пиды, тек = [], {}
for s in вывод.splitlines():
    if s.startswith("CommandLine="):
        тек = {"cmd": s[12:]}
    elif s.startswith("ProcessId=") and тек:
        тек["pid"] = s[10:].strip()
        if "-m sender" in тек["cmd"]:
            пиды.append(тек)
        тек = {}
т = []
for п in пиды:
    т.append("==== pid %s: %s" % (п["pid"], п["cmd"][:200]))
    р = subprocess.run([r"C:\Program Files\Python312\Scripts\py-spy.EXE", "dump", "--pid", п["pid"]],
                       capture_output=True, text=True, errors="replace", timeout=120)
    т.append(р.stdout or р.stderr)
текст = "\n".join(т)
путь = r"C:\sender\_ops\stek-sluzhby-%s.txt" % time.strftime("%Y%m%d-%H%M%S")
open(путь, "w", encoding="utf-8").write(текст)
requests.put(os.environ.get("DROP_URL", "https://parsercompressor.online/drop").rstrip("/") + "/stek-sluzhby.txt",
             data=текст.encode("utf-8"), headers={"X-Drop-Token": os.environ.get("DROP_TOKEN", "")}, timeout=60)
print(путь)
print("\n".join(s for s in текст.splitlines() if s.startswith(("====", "Thread", "Process")))[:3000])
