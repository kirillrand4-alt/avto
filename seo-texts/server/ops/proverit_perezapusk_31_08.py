# -*- coding: utf-8 -*-
"""Только чтение: чем перезапускается служба и в каком она состоянии."""
import glob
import os
import subprocess

print("=== запускалки перезапуска ===")
for кат in (r"C:\sender\_ops", r"C:\sender\server\ops"):
    for п in glob.glob(os.path.join(кат, "*perezapusk*")):
        print("  есть: %s (%d б)" % (п, os.path.getsize(п)))

print("\n=== служба ===")
try:
    r = subprocess.run(["powershell", "-NoProfile", "-Command",
                        "Get-Service | Where-Object {$_.Name -like '*sender*' -or "
                        "$_.DisplayName -like '*sender*'} | "
                        "Select-Object Name,Status,DisplayName | Format-List"],
                       capture_output=True, text=True, timeout=60)
    print(r.stdout.strip()[:600] or "  службы с sender в имени не найдено")
except Exception as ex:
    print("  ", str(ex)[:90])

print("\n=== ИТОГ: время загрузки текущего кода ===")
for ф in (r"C:\sender\sender\store.py", r"C:\sender\sender\sender.py"):
    import datetime
    т = datetime.datetime.fromtimestamp(os.path.getmtime(ф))
    print("  %-32s изменён %s" % (os.path.basename(ф), т.strftime("%Y-%m-%d %H:%M:%S")))
print("  бэкапы:")
for п in sorted(glob.glob(r"C:\sender\sender\*.bak-*"))[-4:]:
    print("     %s" % os.path.basename(п))
