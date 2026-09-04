# -*- coding: utf-8 -*-
"""Только чтение: что связанное с checko сейчас работает и с каких пор."""
import datetime as dt
import glob
import os
import subprocess

пс = ["powershell", "-NoProfile", "-Command"]
зпр = ("Get-CimInstance Win32_Process | Where-Object {"
       " $_.CommandLine -match 'checko|zenno|obhod|obxod' }"
       " | ForEach-Object { \"$($_.ProcessId)|$($_.CreationDate)|\""
       " + $_.CommandLine.Substring(0,[Math]::Min(96,$_.CommandLine.Length)) }")
out = subprocess.run(пс + [зпр], capture_output=True, text=True, timeout=90)
print("=== ПРОЦЕССЫ ПРО CHECKO И ZENNO ===")
print((out.stdout or "").strip() or "(нет)")

print("\n=== ФАЙЛЫ, КОТОРЫЕ ОНИ ПИШУТ ===")
пути = []
for шаб in (r"C:\sender\_ops\*", r"C:\sender\logs\*", r"C:\sender\*.log",
            r"C:\sender\_ops\*.log", r"C:\sender\_ops\*.jsonl"):
    пути.extend(glob.glob(шаб))
сейчас = dt.datetime.now()
свежие = []
for п in set(пути):
    if not os.path.isfile(п):
        continue
    м = dt.datetime.fromtimestamp(os.path.getmtime(п))
    if (сейчас - м).days < 4:
        свежие.append((м, п, os.path.getsize(п)))
for м, п, р in sorted(свежие, reverse=True)[:14]:
    print("  %s %10d Б  %s" % (м.strftime("%m-%d %H:%M"), р, os.path.basename(п)))

print("\n=== СВЕЖЕСТЬ ДАННЫХ CHECKO В БАЗЕ ===")
import sqlite3
e = sqlite3.connect("file:C:/sender/enrich.db?mode=ro", uri=True)
e.row_factory = sqlite3.Row
for р in e.execute("SELECT substr(updated_at,1,10) д, COUNT(*) n FROM requisites"
                   " GROUP BY д ORDER BY д DESC LIMIT 8"):
    print("  requisites обновлено %s: %d строк" % (р["д"], р["n"]))
for р in e.execute("SELECT src, COUNT(*) n FROM requisites GROUP BY src"
                   " ORDER BY n DESC LIMIT 6"):
    print("  источник %-22s %d" % (str(р["src"])[:22], р["n"]))
