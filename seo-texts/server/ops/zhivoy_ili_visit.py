# -*- coding: utf-8 -*-
"""Прогон работает или висит: два замера процессорного времени с паузой.

Один снимок ничего не говорит — процесс может числиться живым и при этом
стоять в ожидании сети. Меряем UserModeTime дважды: растёт значит считает,
стоит значит ждёт ответа шлюза.
"""
import json
import subprocess
import time

КОМАНДА = (
    "Get-CimInstance Win32_Process -Filter \"name like '%python%'\" | "
    "Where-Object {$_.CommandLine -like '*partiya_gen*'} | "
    "Select-Object ProcessId,UserModeTime,KernelModeTime,WorkingSetSize | "
    "ConvertTo-Json -Compress")


def снимок():
    в = subprocess.run(["powershell", "-NoProfile", "-Command", КОМАНДА],
                       capture_output=True, timeout=60)
    т = (в.stdout or b"").decode("utf-8", "replace").strip()
    if not т:
        return {}
    д = json.loads(т)
    д = д if isinstance(д, list) else [д]
    return {int(x["ProcessId"]): x for x in д}


a = снимок()
if not a:
    print("процессов partiya_gen НЕТ — прогон кончился или упал")
    raise SystemExit(0)
time.sleep(30)
b = снимок()
for pid, х in a.items():
    y = b.get(pid)
    if not y:
        print("   pid %s исчез за 30 секунд" % pid)
        continue
    d_user = (y["UserModeTime"] - х["UserModeTime"]) / 1e7
    d_kern = (y["KernelModeTime"] - х["KernelModeTime"]) / 1e7
    print("   pid %-7s процессорного времени за 30 с: user %.2f с, kernel %.2f с"
          % (pid, d_user, d_kern))
    print("   память: %.0f МБ" % (y["WorkingSetSize"] / 1048576.0))
    print("   вывод: %s" % ("СЧИТАЕТ" if d_user > 0.05 else
                            "СТОИТ И ЖДЁТ (сеть или сон)"))
