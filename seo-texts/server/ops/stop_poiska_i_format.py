# -*- coding: utf-8 -*-
"""Снять поиск и выяснить, какие ключи целей ждёт sayty_dlya_celey.py."""
import io
import re
import subprocess
import time

П = r"C:\sender\server\ops\sayty_dlya_celey.py"

пиды = subprocess.run(
    ["powershell", "-NoProfile", "-Command",
     "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like "
     "'*sayty_dlya_celey*' } | ForEach-Object { $_.ProcessId }"],
    capture_output=True, text=True, timeout=90).stdout.split()
for п in пиды:
    if п.isdigit():
        subprocess.run(["powershell", "-NoProfile", "-Command",
                        "Stop-Process -Id %s -Force" % п],
                       capture_output=True, text=True, timeout=60)
time.sleep(3)

т = io.open(П, encoding="utf-8", errors="replace").read()
стр = т.splitlines()

print("=" * 78)
print("=== СВОДКА: ФОРМАТ ЦЕЛЕЙ ===")
print("снято процессов поиска: %s" % (", ".join(пиды) if пиды else "не было"))
print("")
print("--- где читаются цели и какие ключи берутся ---")
for i, с in enumerate(стр, 1):
    if re.search(r"(ЦЕЛИ|json\.loads|c\[|c\.get|имя\s*=|company|работа)", с) \
            and not с.strip().startswith("#"):
        print("%4d| %s" % (i, с[:150]))
    if i > 150:
        break

# какие ключи в СТАРОМ файле целей, на который скрипт рассчитан
СТАРЫЙ = r"C:\seostat\drop\celi_bez_tehlpr.jsonl"
print("")
print("--- образец СТАРОГО файла целей %s ---" % СТАРЫЙ)
try:
    with io.open(СТАРЫЙ, encoding="utf-8", errors="replace") as ф:
        for i, с in enumerate(ф):
            if с.strip():
                print("   " + с.strip()[:300])
            if i >= 2:
                break
except Exception as ex:                                        # noqa: BLE001
    print("   не прочитался: %s" % str(ex)[:80])

print("")
print("--- образец МОЕГО файла целей ---")
try:
    with io.open(r"C:\seostat\drop\celi_meyer_30mln.jsonl",
                 encoding="utf-8", errors="replace") as ф:
        for i, с in enumerate(ф):
            if с.strip():
                print("   " + с.strip()[:300])
            if i >= 1:
                break
except Exception as ex:                                        # noqa: BLE001
    print("   не прочитался: %s" % str(ex)[:80])
