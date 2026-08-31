# -*- coding: utf-8 -*-
"""Итог пробного блока: письма, цена, скорость."""
import glob
import io
import os
import re
import subprocess
import time

п = sorted(glob.glob(r"C:\sender\_ops\partiya_gen-0831-1630*.log"),
           key=os.path.getmtime, reverse=True)[0]
с = io.open(п, encoding="utf-8", errors="replace").read().splitlines()
print("лог %s: %d строк, изменён %.1f мин назад"
      % (os.path.basename(п), len(с), (time.time() - os.path.getmtime(п)) / 60))
письма = [x for x in с if re.match(r"\s*\[\d+/\d+\]", x)]
print("\nстрок с письмами: %d" % len(письма))
for x in письма[-10:]:
    print("   %s" % x.strip()[:150])
итог = [x for x in с if x.strip().startswith("итог:")]
print("\nитоговая строка: %s" % (итог[-1].strip() if итог else "прогон ещё идёт"))

r = subprocess.run(["powershell", "-NoProfile", "-Command",
                    "(Get-CimInstance Win32_Process -Filter \"Name like 'python%'\" | "
                    "Where-Object { $_.CommandLine -like '*partiya_gen*' }).Count"],
                   capture_output=True, text=True, timeout=90)
живых = (r.stdout or "").strip()

# сколько писем этого блока реально легло в очередь
import sqlite3
c = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\sender.db", uri=True,
                    timeout=60)
n = c.execute("SELECT COUNT(*) FROM confirm_reviews WHERE campaign_id=11"
              "  AND created_at >= '2026-08-31T16:30'").fetchone()[0]
c.close()

print("\n=== ИТОГ ===")
print("живых прогонов: %s" % живых)
print("карточек кампании 11 после 16:30: %d" % n)
