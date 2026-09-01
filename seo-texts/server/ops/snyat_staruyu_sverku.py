# -*- coding: utf-8 -*-
"""Снять экземпляр сверки, идущий со старым кодом, и проверить замок.

Скрипт идемпотентный по своему замыслу, поэтому обрыв ничего не портит:
следующий прогон доделает. Снимаем именно потому, что этот экземпляр
делает уже убранную работу — переписывает все 6575 вердиктов.
"""
import sqlite3
import subprocess
import time

БАЗА = r"C:\sender\enrich.db"


def пш(ком):
    return subprocess.run(["powershell", "-NoProfile", "-Command", ком],
                          capture_output=True, text=True, timeout=90).stdout.strip()


def замок(терпение=20):
    t0 = time.time()
    try:
        c = sqlite3.connect(БАЗА, timeout=терпение, isolation_level=None)
        c.execute("PRAGMA busy_timeout = %d" % (терпение * 1000))
        c.execute("BEGIN IMMEDIATE")
        c.execute("ROLLBACK")
        c.close()
        return "СВОБОДЕН (взят за %.2f с)" % (time.time() - t0)
    except Exception as ex:                                    # noqa: BLE001
        return "занят (%.1f с): %s" % (time.time() - t0, str(ex)[:45])


до = замок(10)
пиды = пш("Get-CimInstance Win32_Process | Where-Object { $_.CommandLine "
          "-like '*sverka_prigovorov*' -or $_.CommandLine -like "
          "'*sverka-prigovorov*' } | ForEach-Object { $_.ProcessId }").split()
for п in пиды:
    if п.isdigit():
        пш("Stop-Process -Id %s -Force" % п)
time.sleep(5)
после = замок(25)
осталось = пш("Get-CimInstance Win32_Process | Where-Object { $_.CommandLine "
              "-like '*sverka_prigovorov*' } | ForEach-Object { $_.ProcessId }")

r = sqlite3.connect("file:%s?mode=ro" % БАЗА, uri=True, timeout=60)
наших = r.execute(
    "SELECT COUNT(*) FROM requisites WHERE src='checko-sbor-agro'").fetchone()[0]
r.close()

print("=" * 70)
print("=== СВОДКА: СНЯТИЕ СТАРОЙ СВЕРКИ ===")
print("замок ДО:    %s" % до)
print("снято процессов: %s" % (", ".join(пиды) if пиды else "не было"))
print("замок ПОСЛЕ: %s" % после)
print("осталось процессов сверки: %s" % (осталось or "ни одного"))
print("")
print("строк заливки в requisites: %d" % наших)
