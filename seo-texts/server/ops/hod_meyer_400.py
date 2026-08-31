# -*- coding: utf-8 -*-
"""Как идёт прогон Meyer: процесс, лог, сколько уже в очереди."""
import glob
import io
import os
import sqlite3
import subprocess
import time

r = subprocess.run(["powershell", "-NoProfile", "-Command",
                    "Get-CimInstance Win32_Process -Filter \"Name like 'python%'\" | "
                    "Where-Object { $_.CommandLine -like '*partiya_gen*' } | "
                    "ForEach-Object { \"$($_.ProcessId) :: $($_.CommandLine)\" }"],
                   capture_output=True, text=True, timeout=90)
живые = [с for с in (r.stdout or "").splitlines() if с.strip()]
print("=== ПРОЦЕССЫ ===")
for с in живые:
    print("   %s" % с.strip()[:190])
if not живые:
    print("   прогонов нет")

логи = sorted(glob.glob(r"C:\sender\_ops\partiya_gen-*.log"),
              key=os.path.getmtime, reverse=True)[:1]
for п in логи:
    print("\n=== ЛОГ %s (%.1f мин назад, %d Б) ==="
          % (os.path.basename(п), (time.time() - os.path.getmtime(п)) / 60.0,
             os.path.getsize(п)))
    с = io.open(п, encoding="utf-8", errors="replace").read().splitlines()
    for x in с[:8]:
        print("   %s" % x[:150])
    if len(с) > 16:
        print("   …")
        for x in с[-10:]:
            print("   %s" % x[:150])

c = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\sender.db", uri=True,
                    timeout=60)
print("\n=== ОЧЕРЕДЬ ЗА ПОСЛЕДНИЙ ЧАС ===")
for r_ in c.execute("SELECT campaign_id, status, COUNT(*) n FROM confirm_reviews"
                    " WHERE created_at >= datetime('now','-1 hour')"
                    " GROUP BY campaign_id, status"):
    print("   кампания %-4s %-12s %5d" % r_)
итог = c.execute("SELECT COUNT(*) FROM confirm_reviews WHERE campaign_id=11"
                 "  AND created_at >= datetime('now','-1 hour')").fetchone()[0]
c.close()
print("\n=== ИТОГ ===")
print("живых прогонов: %d" % len(живые))
print("писем Meyer в очереди за час: %d из 400" % итог)
