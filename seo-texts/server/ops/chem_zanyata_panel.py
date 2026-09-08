# -*- coding: utf-8 -*-
"""Чем занята панель прямо сейчас: отправка, пробы, нагрузка процесса."""
import subprocess, sys, time
from collections import Counter
sys.path.insert(0, r"C:\sender")
from sender.store import Store                                  # noqa: E402

store = Store(r"C:\sender\sender.db")
print("местное время: %s" % time.strftime("%H:%M:%S"))
с = Counter()
with store._lock:
    for окно, вырез in (("за 10 минут", "-10 minutes"),
                        ("за 60 минут", "-60 minutes")):
        n = store._conn.execute(
            "SELECT COUNT(*) FROM messages WHERE status='sent' "
            "  AND sent_at >= datetime('now', ?)", (вырез,)).fetchone()[0]
        print("   отправлено %s: %d" % (окно, n))
    for р in store._conn.execute(
            "SELECT status, COUNT(*) c FROM messages "
            " WHERE status IN ('sending','scheduled') GROUP BY status"):
        с[str(р["status"])] = int(р["c"])
print("   сейчас в работе: %s" % dict(с))

ком = ("Get-CimInstance Win32_PerfFormattedData_PerfProc_Process | "
       "Where-Object {$_.Name -like 'python*'} | "
       "Select-Object Name,IDProcess,PercentProcessorTime,WorkingSetPrivate | "
       "Format-Table -AutoSize | Out-String -Width 120")
r = subprocess.run(["powershell", "-NoProfile", "-Command", ком],
                   capture_output=True, timeout=120)
т = (r.stdout or b"").decode("cp866", errors="replace")
if not т.strip():
    т = (r.stdout or b"").decode("utf-8", errors="replace")
print("")
print("--- нагрузка python-процессов ---")
print(т.strip()[:1200])

# сколько потоков у панели и жив ли цикл автоотправки
ком2 = ("Get-Process -Id (Get-CimInstance Win32_Process -Filter "
        "\"Name='python.exe' AND CommandLine LIKE '%serve-api%'\").ProcessId | "
        "Select-Object Id,Threads,CPU,WS | Format-List")
r2 = subprocess.run(["powershell", "-NoProfile", "-Command", ком2],
                    capture_output=True, timeout=120)
т2 = (r2.stdout or b"").decode("cp866", errors="replace")
if not т2.strip():
    т2 = (r2.stdout or b"").decode("utf-8", errors="replace")
print("")
print("--- процесс панели ---")
print(т2.strip()[:600])
