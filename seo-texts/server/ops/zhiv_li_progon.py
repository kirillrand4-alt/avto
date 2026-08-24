# -*- coding: utf-8 -*-
"""Идёт ли сейчас прогон генерации: процессы и свежесть журнала.

Запускающая команда оборвалась по таймауту с моей стороны - но прогон
отцеплённый, он мог стартовать и жить. Прежде чем запускать второй раз (а
это деньги), надо посмотреть, не идёт ли уже первый.
"""
import glob
import os
import subprocess
import time

из = subprocess.run(
    ["powershell", "-NoProfile", "-Command",
     "Get-CimInstance Win32_Process -Filter \"Name like 'python%'\" | "
     "Select-Object ProcessId,CreationDate,CommandLine | "
     "ConvertTo-Csv -NoTypeInformation"],
    capture_output=True, text=True, timeout=90)
print("=== процессы python ===")
for строка in (из.stdout or "").splitlines():
    if "partiya_gen" in строка or "_ops" in строка:
        print("  " + строка.strip()[:190])

print("\n=== свежие файлы журнала и вывода ===")
for шаблон in (r"C:\sender\_ops\*.jsonl", r"C:\sender\_ops\*.out",
               r"C:\sender\_ops\*.log"):
    for п in glob.glob(шаблон):
        возраст = time.time() - os.path.getmtime(п)
        if возраст < 7200:
            print(f"  {os.path.basename(п):<44} {os.path.getsize(п):>9} байт, "
                  f"обновлён {int(возраст//60)} мин назад")
