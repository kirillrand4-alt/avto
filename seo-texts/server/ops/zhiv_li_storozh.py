# -*- coding: utf-8 -*-
"""Пережил ли сторож перезапуск песочницы и что он успел."""
import glob
import io
import os
import re
import subprocess
import time

print("=== ПРОЦЕССЫ ===")
r = subprocess.run(["powershell", "-NoProfile", "-Command",
                    "Get-CimInstance Win32_Process -Filter \"Name like 'python%'\" | "
                    "Where-Object { $_.CommandLine -like '*nochnoy_storozh*' -or "
                    "$_.CommandLine -like '*partiya_gen*' } | "
                    "ForEach-Object { \"$($_.ProcessId) :: $($_.CommandLine)\" }"],
                   capture_output=True, text=True, timeout=90)
строки = [с.strip() for с in (r.stdout or "").splitlines() if с.strip()]
for с in строки:
    print("   %s" % с[:170])
if not строки:
    print("   ни сторожа, ни прогона")

ж = r"C:\sender\_ops\nochnoy-storozh.log"
print("\n=== ЖУРНАЛ СТОРОЖА ===")
if os.path.exists(ж):
    с = io.open(ж, encoding="utf-8", errors="replace").read().splitlines()
    print("   строк: %d, изменён %.1f мин назад"
          % (len(с), (time.time() - os.path.getmtime(ж)) / 60))
    for x in с[-12:]:
        print("   %s" % x[:160])
else:
    print("   журнала нет")

print("\n=== СВЕЖИЕ ЛОГИ ПРОГОНОВ ===")
for п in sorted(glob.glob(r"C:\sender\_ops\partiya_gen-*.log"),
                key=os.path.getmtime, reverse=True)[:2]:
    с = io.open(п, encoding="utf-8", errors="replace").read().splitlines()
    письма = [x for x in с if re.match(r"\s*\[\d+/\d+\]", x)]
    итог = [x for x in с if x.strip().startswith("итог:")]
    print("   %-34s %.1f мин назад, строк %d, писем %d %s"
          % (os.path.basename(п), (time.time() - os.path.getmtime(п)) / 60,
             len(с), len(письма),
             ("| %s" % итог[-1].strip()[:60]) if итог else ""))
    for x in письма[-4:]:
        print("      %s" % x.strip()[:150])
print("\n=== ИТОГ ===")
print("сторож в процессах: %s"
      % ("да" if any("nochnoy_storozh" in с for с in строки) else "НЕТ"))
