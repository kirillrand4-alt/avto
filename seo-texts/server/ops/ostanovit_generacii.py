# -*- coding: utf-8 -*-
"""Остановить все фоновые генерации (владелец 12.10: «сначала перестанем
жечь деньги просто так»). Письма, уже легшие в очередь, не трогаем."""
import subprocess

в = subprocess.run(["wmic", "process", "where", "name='python.exe'", "get",
                    "ProcessId,CommandLine"], capture_output=True, text=True).stdout
убиты = []
for с in в.splitlines():
    if ("generaciya_500" in с or "sravnit_modeli" in с) and "wmic" not in с:
        pid = с.split()[-1]
        if pid.isdigit():
            subprocess.run(["taskkill", "/PID", pid, "/T", "/F"],
                           capture_output=True)
            убиты.append((pid, "generaciya_500" if "generaciya" in с else "sravnit_modeli"))
for pid, что in убиты:
    print("   остановлен %s (pid %s)" % (что, pid))
в = subprocess.run(["wmic", "process", "where", "name='python.exe'", "get",
                    "ProcessId,CommandLine"], capture_output=True, text=True).stdout
осталось = [с for с in в.splitlines() if "generaciya_500" in с or "sravnit_modeli" in с]
print("=== ОСТАНОВЛЕНО: %d, осталось живых генераций: %d ===" % (len(убиты), len(осталось)))
