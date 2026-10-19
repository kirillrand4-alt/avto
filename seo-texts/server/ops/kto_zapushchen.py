# -*- coding: utf-8 -*-
"""Какие python-процессы сейчас идут на сервере: pid, старт, процессор, скрипт и
его именованные аргументы (только имена ключей и модели — без значений-секретов)."""
import json
import re
import subprocess
р = subprocess.run(["powershell", "-NoProfile", "-Command",
                    "Get-CimInstance Win32_Process -Filter \"Name like 'python%'\" | "
                    "Select-Object ProcessId,ParentProcessId,CreationDate,CommandLine | ConvertTo-Json -Depth 2"],
                   capture_output=True, text=True, encoding="utf-8", errors="replace")
д = json.loads(р.stdout or "[]")
д = д if isinstance(д, list) else [д]
for x in д:
    кс = str(x.get("CommandLine") or "")
    скрипт = re.findall(r"[\w\\:.-]+\.py", кс)
    модель = re.findall(r"claude-[\w.-]+", кс)
    print(x.get("ProcessId"), "<-", x.get("ParentProcessId"), str(x.get("CreationDate"))[:25],
          " ".join(s.split("\\")[-1] for s in скрипт[:3]), модель, "-m sender" if "-m sender" in кс else "")
