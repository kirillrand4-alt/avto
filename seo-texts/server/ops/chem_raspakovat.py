# -*- coding: utf-8 -*-
"""Чем на сервере распаковать RAR5 и куда класть исходники."""
import glob
import os
import shutil
import subprocess

for имя in ("7z", "7za", "7z.exe", "WinRAR", "unrar", "rar"):
    print("%-10s %s" % (имя, shutil.which(имя) or "не в PATH"))
for п in (r"C:\Program Files\7-Zip\7z.exe",
          r"C:\Program Files (x86)\7-Zip\7z.exe",
          r"C:\Program Files\WinRAR\WinRAR.exe",
          r"C:\Program Files\WinRAR\UnRAR.exe"):
    print("%-46s %s" % (п, "ЕСТЬ" if os.path.exists(п) else "нет"))
try:
    в = subprocess.run(["powershell", "-NoProfile", "-Command",
                        "Get-Command Expand-Archive | Select-Object Name"],
                       capture_output=True, timeout=30)
    print("Expand-Archive: %s"
          % (в.stdout or b"").decode("cp866", "replace").strip()[:60])
except Exception as e:  # noqa: BLE001
    print("powershell: %s" % str(e)[:60])
print("\nсвободно в C:\\sender: %.1f ГБ"
      % (shutil.disk_usage(r"C:\sender").free / 1073741824.0))
