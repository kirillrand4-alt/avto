# -*- coding: utf-8 -*-
"""Диагноз WAL: почему не сбрасывается и кто держит снимок. Сводка в конце.

Контрольную точку пробуем ТОЛЬКО пассивную (PASSIVE) — она делает что может
и никого не блокирует. Ничего не убиваем: сперва понять, потом чинить.
"""
import os
import sqlite3
import subprocess
import time

БАЗА = r"C:\sender\enrich.db"


def пш(ком):
    r = subprocess.run(["powershell", "-NoProfile", "-Command", ком],
                       capture_output=True, text=True, timeout=120)
    return (r.stdout or "").strip()


def размеры():
    д = {}
    for суф in ("", "-wal", "-shm"):
        п = БАЗА + суф
        д[суф or "база"] = os.path.getsize(п) if os.path.exists(п) else 0
    return д


до = размеры()

# кто открыл файл базы — по дескрипторам не достанем без handle.exe,
# поэтому смотрим процессы, которые вообще могут с ней работать
проц = пш(
    "Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | "
    "ForEach-Object { "
    "  $мин = [int]((New-TimeSpan -Start $_.CreationDate -End (Get-Date))"
    ".TotalMinutes); "
    "  \"$($_.ProcessId)|$мин|\" + "
    "$_.CommandLine.Substring(0,[Math]::Min(88,$_.CommandLine.Length)) }")

# пассивная контрольная точка
итог_чек = ""
try:
    c = sqlite3.connect(БАЗА, timeout=30)
    c.execute("PRAGMA busy_timeout = 30000")
    r = c.execute("PRAGMA wal_checkpoint(PASSIVE)").fetchone()
    итог_чек = ("busy=%s страниц_в_wal=%s перенесено=%s" % r)
    авто = c.execute("PRAGMA wal_autocheckpoint").fetchone()[0]
    режим = c.execute("PRAGMA journal_mode").fetchone()[0]
    c.close()
except Exception as ex:                                        # noqa: BLE001
    итог_чек = "не вышло: %s" % str(ex)[:90]
    авто, режим = "?", "?"

time.sleep(3)
после = размеры()

print("=" * 70)
print("=== СВОДКА: ДИАГНОЗ WAL ===")
print("сейчас: %s" % time.strftime("%d.%m %H:%M:%S"))
print("")
print("размеры файлов:")
for к in ("база", "-wal", "-shm"):
    print("   %-6s было %13d Б  стало %13d Б  (%+d)"
          % (к, до[к], после[к], после[к] - до[к]))
print("")
print("режим журнала: %s; автоконтрольная точка каждые %s страниц"
      % (режим, авто))
print("пассивная контрольная точка: %s" % итог_чек)
print("   busy=1 значит: кто-то держит снимок, перенести всё не дали")
print("")
print("живые питоны (PID | минут работает | команда):")
for с in (проц or "").splitlines():
    print("   " + с[:110])
