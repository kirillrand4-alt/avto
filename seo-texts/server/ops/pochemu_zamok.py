# -*- coding: utf-8 -*-
"""Почему enrich.db в замке: режим журнала и как открывают её штатные писцы."""
import io
import os
import re
import sqlite3
import subprocess

БАЗА = r"C:\sender\enrich.db"

c = sqlite3.connect("file:%s?mode=ro" % БАЗА, uri=True, timeout=30)
режим = c.execute("PRAGMA journal_mode").fetchone()[0]
синх = c.execute("PRAGMA synchronous").fetchone()[0]
c.close()

рядом = []
for имя in os.listdir(os.path.dirname(БАЗА)):
    if имя.startswith("enrich.db"):
        п = os.path.join(os.path.dirname(БАЗА), имя)
        рядом.append((имя, os.path.getsize(п)))

# как открывает базу штатный модуль
edb = r"C:\sender\server\enrich_db.py"
куски = []
if os.path.exists(edb):
    т = io.open(edb, encoding="utf-8", errors="replace").read()
    for м in re.finditer(r"(journal_mode|busy_timeout|synchronous|connect\(|"
                         r"isolation_level|timeout=)", т):
        н = т.rfind("\n", 0, м.start())
        к = т.find("\n", м.end())
        куски.append(т[н + 1:к].strip()[:130])

# кто сейчас держит файл
держат = subprocess.run(
    ["powershell", "-NoProfile", "-Command",
     "Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | "
     "ForEach-Object { \"$($_.ProcessId)|\" + "
     "$_.CommandLine.Substring(0,[Math]::Min(90,$_.CommandLine.Length)) }"],
    capture_output=True, text=True, timeout=90).stdout.strip()

# проба записи: успеем ли за 5 секунд
проба = ""
try:
    w = sqlite3.connect(БАЗА, timeout=5)
    w.execute("PRAGMA busy_timeout = 5000")
    w.execute("CREATE TABLE IF NOT EXISTS _proba_zamka (x INTEGER)")
    w.execute("INSERT INTO _proba_zamka VALUES (1)")
    w.commit()
    w.execute("DROP TABLE _proba_zamka")
    w.commit()
    w.close()
    проба = "ЗАПИСЬ ПРОШЛА за 5 секунд"
except Exception as ex:                                        # noqa: BLE001
    проба = "ЗАПИСЬ НЕ ПРОШЛА: %s" % str(ex)[:90]

print("=" * 68)
print("=== СВОДКА: ЗАМОК enrich.db ===")
print("режим журнала: %s   synchronous=%s" % (режим, синх))
print("файлы рядом с базой:")
for имя, рз in рядом:
    print("   %-24s %12d Б" % (имя, рз))
print("")
print("проба записи: %s" % проба)
print("")
print("как открывает базу штатный enrich_db.py:")
for с in dict.fromkeys(куски):
    print("   %s" % с)
print("")
print("живые питоны (кандидаты в держатели замка):")
for с in (держат or "").splitlines():
    print("   " + с[:100])
