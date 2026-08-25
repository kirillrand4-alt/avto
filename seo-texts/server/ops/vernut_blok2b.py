# -*- coding: utf-8 -*-
"""Вернуть блок КЦ в работу: я остановил его зря.

Строки в .err — это предупреждения о РЕТРАЕ («сбой провайдера, ретрай 1/1
через 15 с»), а не отказ: 28 таких на 445 писем, и после ретрая письмо
выходило. Главный лог всё это время шёл нормально: [445/2300], письма по
$0.10-0.32. Я посмотрел только .err и убил рабочий прогон.

Резюм по журналу сохраняет написанное: перезапуск продолжит с того места,
где остановился, а не начнёт заново.
"""
import os
import subprocess
import time

КАТАЛОГ = r"C:\sender\_ops"
ПИТОН = r"C:\Program Files\Python311\python.exe"
лог = os.path.join(КАТАЛОГ, "ochered2508-blok2c-kc.log")
аргументы = [os.path.join(КАТАЛОГ, "partiya_gen.py"),
             "2300", "48000", "kc", "0", "porog=2.50",
             "model=claude-sonnet-4-6", "--bez-predklassa"]
команда = ("Start-Process -FilePath '%s' -ArgumentList '%s' "
           "-WorkingDirectory '%s' -WindowStyle Hidden "
           "-RedirectStandardOutput '%s' -RedirectStandardError '%s'"
           % (ПИТОН, "','".join(аргументы), КАТАЛОГ, лог, лог + ".err"))
з = subprocess.run(["powershell", "-NoProfile", "-Command", команда],
                   capture_output=True, timeout=60)
print("запуск: rc=%s %s"
      % (з.returncode, (з.stdout or з.stderr).decode("cp866", "replace")[:160]))
time.sleep(8)
п = subprocess.run(
    ["powershell", "-NoProfile", "-Command",
     "Get-CimInstance Win32_Process -Filter \"name like '%python%'\" | "
     "Where-Object {$_.CommandLine -like '*partiya_gen*'} | "
     "Select-Object ProcessId,CommandLine | Format-List"],
    capture_output=True, timeout=60)
print((п.stdout or b"").decode("cp866", "replace")[:400])
