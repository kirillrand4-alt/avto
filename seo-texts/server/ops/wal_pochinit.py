# -*- coding: utf-8 -*-
"""Усечь WAL и показать, кто держит файл базы открытым. Сводка в конце.

Обычная контрольная точка (PASSIVE/FULL) переносит страницы в базу, но файл
WAL НЕ укорачивает — он остаётся прежнего размера и переиспользуется. Чтобы
файл реально уменьшился, нужна TRUNCATE: она берёт короткий монопольный
замок и обнуляет файл. Если кто-то в этот момент читает — вернёт busy=1,
и это не поломка, а «попробуй позже».

Держателей файла ищем через handle.exe, если он есть; иначе честно говорим,
что списка дескрипторов нет, и судим по результату контрольной точки.
"""
import os
import shutil
import sqlite3
import subprocess
import time

БАЗА = r"C:\sender\enrich.db"


def пш(ком, т=120):
    r = subprocess.run(["powershell", "-NoProfile", "-Command", ком],
                       capture_output=True, text=True, timeout=т)
    return (r.stdout or "").strip(), (r.stderr or "").strip()[:200]


def размер(суф=""):
    п = БАЗА + суф
    return os.path.getsize(п) if os.path.exists(п) else 0


до_база, до_вал = размер(), размер("-wal")

# --- кто держит файл открытым -------------------------------------------
держатели = ""
способ = ""
handle = None
for кандидат in (r"C:\Windows\System32\handle.exe", r"C:\tools\handle.exe",
                 r"C:\seostat\handle.exe", r"C:\sender\handle.exe"):
    if os.path.exists(кандидат):
        handle = кандидат
        break
if not handle:
    handle = shutil.which("handle") or shutil.which("handle64")
if handle:
    способ = "handle.exe (%s)" % handle
    вых, _ = пш("& '%s' -nobanner -accepteula 'enrich.db' 2>&1" % handle, 150)
    держатели = вых
else:
    способ = "handle.exe не найден"
    # запасной путь: у кого в командной строке фигурирует enrich или sender
    держатели, _ = пш(
        "Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | "
        "Where-Object { $_.CommandLine -like '*enrich*' -or "
        "$_.CommandLine -like '*sender*' } | ForEach-Object { "
        "  $мин = [int]((New-TimeSpan -Start $_.CreationDate -End (Get-Date))"
        ".TotalMinutes); \"$($_.ProcessId)|$мин мин|\" + "
        "$_.CommandLine.Substring(0,[Math]::Min(76,$_.CommandLine.Length)) }")

# --- усечение -----------------------------------------------------------
шаги = []
for вид in ("TRUNCATE", "RESTART", "TRUNCATE"):
    try:
        c = sqlite3.connect(БАЗА, timeout=60)
        c.execute("PRAGMA busy_timeout = 60000")
        r = c.execute("PRAGMA wal_checkpoint(%s)" % вид).fetchone()
        c.close()
        шаги.append("%-8s -> busy=%s страниц=%s перенесено=%s  (wal %d Б)"
                    % (вид, r[0], r[1], r[2], размер("-wal")))
        if вид == "TRUNCATE" and r[0] == 0 and размер("-wal") < 10_000_000:
            break
    except Exception as ex:                                    # noqa: BLE001
        шаги.append("%-8s -> ошибка: %s" % (вид, str(ex)[:80]))
    time.sleep(2)

после_база, после_вал = размер(), размер("-wal")

print("=" * 70)
print("=== СВОДКА: ПОЧИНКА WAL ===")
print("сейчас: %s" % time.strftime("%d.%m %H:%M:%S"))
print("")
print("шаги контрольной точки:")
for с in шаги:
    print("   " + с)
print("")
print("размеры:")
print("   база: %13d -> %13d Б  (%+d)"
      % (до_база, после_база, после_база - до_база))
print("   WAL:  %13d -> %13d Б  (%+d)"
      % (до_вал, после_вал, после_вал - до_вал))
print("")
print("=== КТО ДЕРЖИТ ФАЙЛ ОТКРЫТЫМ ===")
print("способ: %s" % способ)
for с in (держатели or "   пусто").splitlines()[:24]:
    print("   " + с[:120])
