# -*- coding: utf-8 -*-
"""Только СМОТРИМ: есть ли на сервере способ перезапустить службу и права на это.

Ничего не перезапускаем — узнаём, кто мы, что за служба, и делал ли это кто-то
до нас (соседняя сессия).
"""
import ctypes
import getpass
import io
import os
import subprocess

print("процесс работает от: %s" % getpass.getuser())
try:
    админ = bool(ctypes.windll.shell32.IsUserAnAdmin())
except Exception as ex:
    админ = "не спросить: %s" % ex
print("права администратора: %s" % админ)

try:
    r = subprocess.run(["sc.exe", "query", "SenderPanel"], capture_output=True,
                       text=True, timeout=30)
    print("--- sc query SenderPanel (код %s) ---" % r.returncode)
    print((r.stdout or r.stderr).strip()[:600])
except Exception as ex:
    print("sc query не вышло: %s" % ex)

try:
    r = subprocess.run(
        ["powershell", "-NoProfile", "-Command",
         "(Get-Service SenderPanel | Select-Object Status,StartType,Name "
         "| Format-List | Out-String).Trim()"],
        capture_output=True, text=True, timeout=60)
    print("--- Get-Service (код %s) ---" % r.returncode)
    print((r.stdout or r.stderr).strip()[:400])
except Exception as ex:
    print("powershell не вышло: %s" % ex)

# следы чужих перезапусков в наших же ops
следы = []
for корень in (r"C:\sender\server\ops", r"C:\sender\_ops"):
    if not os.path.isdir(корень):
        continue
    for имя in os.listdir(корень):
        if not имя.endswith(".py"):
            continue
        п = os.path.join(корень, имя)
        try:
            т = io.open(п, encoding="utf-8", errors="ignore").read()
        except Exception:
            continue
        if "Restart-Service" in т or "SenderPanel" in т and "sc.exe" in т:
            следы.append(имя)
print("\nскрипты, где уже упоминается перезапуск службы: %s"
      % (", ".join(следы[:20]) or "нет"))
