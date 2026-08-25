# -*- coding: utf-8 -*-
"""Что за «пиксель»: кто его запускает, что он делает, как давно падает."""
import glob
import io
import os
import subprocess
import time

print("=== файлы pixel в _ops ===")
for п in sorted(glob.glob(r"C:\sender\_ops\pixel*")):
    print("   %-46s %8d б  %s" % (os.path.basename(п), os.path.getsize(п),
                                  time.strftime("%d.%m %H:%M",
                                                time.localtime(os.path.getmtime(п)))))
print("")
print("=== кто его пускает: задания планировщика ===")
out = subprocess.run(
    ["powershell", "-NoProfile", "-Command",
     "Get-ScheduledTask | Where-Object { $_.TaskName -like '*pix*' -or "
     "$_.Actions.Arguments -like '*pixel*' } | "
     "ForEach-Object { $_.TaskName + ' | ' + $_.State + ' | ' + "
     "($_.Actions | ForEach-Object { $_.Execute + ' ' + $_.Arguments }) }"],
    capture_output=True, text=True, timeout=90)
print((out.stdout or "").strip()[:1500] or "   задач с «pixel» не нашлось")
print((out.stderr or "").strip()[:300])
print("")
print("=== службы со словом pixel ===")
out2 = subprocess.run(
    ["powershell", "-NoProfile", "-Command",
     "Get-Service | Where-Object { $_.Name -like '*pix*' } | "
     "Select-Object Name,Status | Format-List"],
    capture_output=True, text=True, timeout=60)
print((out2.stdout or "").strip()[:600] or "   служб нет")
print("")
для = r"C:\sender\_ops\pixel.err.log"
if os.path.exists(для):
    т = io.open(для, encoding="utf-8", errors="replace").read()
    print("=== в err-логе %d знаков, сколько раз падал ===" % len(т))
    print("   «Traceback» встречается: %d" % т.count("Traceback"))
    print("   первый и последний куски:")
    for с in т.splitlines()[:6]:
        print("   " + с[:150])
    print("   ...")
    for с in т.splitlines()[-6:]:
        print("   " + с[:150])
