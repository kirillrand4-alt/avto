# -*- coding: utf-8 -*-
"""Сколько компаний свежего сбора прошли порог 30 млн — прибавка к пулу."""
import sqlite3
import subprocess
from collections import Counter

проц = subprocess.run(
    ["powershell", "-NoProfile", "-Command",
     "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like "
     "'*dolit_iz_zhurnala*' -or $_.CommandLine -like '*checko_finansy*' } | "
     "ForEach-Object { $м = [int]((New-TimeSpan -Start $_.CreationDate "
     "-End (Get-Date)).TotalMinutes); \"PID $($_.ProcessId) $м мин | \" + "
     "$_.CommandLine.Substring(0,[Math]::Min(60,$_.CommandLine.Length)) }"],
    capture_output=True, text=True, timeout=90).stdout.strip()

c = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\enrich.db", uri=True,
                    timeout=120)
всего = c.execute(
    "SELECT COUNT(*) FROM requisites WHERE src='checko-sbor-agro'").fetchone()[0]
разрез = Counter()
for (в,) in c.execute(
        "SELECT revenue_rub FROM requisites WHERE src='checko-sbor-agro'"):
    с = str(в or "").strip()
    if с in ("", "0"):
        разрез["выручка ещё не добыта"] += 1
        continue
    try:
        ч = int(с)
    except ValueError:
        разрез["не число"] += 1
        continue
    if ч >= 100_000_000:
        разрез["от 100 млн"] += 1
    elif ч >= 30_000_000:
        разрез["30-100 млн"] += 1
    else:
        разрез["ниже 30 млн"] += 1
# сколько из прошедших порог уже есть в companies (то есть могут попасть в письма)
проходят = c.execute(
    "SELECT COUNT(*) FROM requisites WHERE src='checko-sbor-agro' "
    "  AND CAST(COALESCE(revenue_rub,'0') AS INTEGER) >= 30000000"
).fetchone()[0]
в_обогащении = c.execute(
    "SELECT COUNT(*) FROM requisites r JOIN companies k ON k.inn=r.inn "
    " WHERE r.src='checko-sbor-agro' "
    "   AND CAST(COALESCE(r.revenue_rub,'0') AS INTEGER) >= 30000000"
).fetchone()[0]
с_почтой = c.execute(
    "SELECT COUNT(*) FROM requisites r JOIN companies k ON k.inn=r.inn "
    " WHERE r.src='checko-sbor-agro' "
    "   AND CAST(COALESCE(r.revenue_rub,'0') AS INTEGER) >= 30000000 "
    "   AND COALESCE(k.best_email,'') <> ''"
).fetchone()[0]
почта_у_чеко = c.execute(
    "SELECT COUNT(*) FROM requisites WHERE src='checko-sbor-agro' "
    "  AND CAST(COALESCE(revenue_rub,'0') AS INTEGER) >= 30000000 "
    "  AND COALESCE(emails_checko,'') <> ''"
).fetchone()[0]
c.close()

print("=" * 74)
print("=== СВОДКА: ПРИБАВКА ИЗ СВЕЖЕГО СБОРА ===")
print("процессы: %s" % (проц if проц else "ни одного"))
print("")
print("компаний свежего сбора в requisites: %d" % всего)
for к, в in разрез.most_common():
    print("   %-26s %7d  (%4.1f%%)" % (к, в, 100.0 * в / всего if всего else 0))
print("")
print("=== ПРОШЛИ ПОРОГ 30 МЛН: %d ===" % проходят)
print("   из них уже заведены в companies:   %6d" % в_обогащении)
print("   из них с почтой в companies:       %6d" % с_почтой)
print("   у скольких Чеко отдал почту:       %6d   <- можно завести"
      % почта_у_чеко)
