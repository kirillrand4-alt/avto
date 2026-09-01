# -*- coding: utf-8 -*-
"""Две компании в один поток: забрать счётчики отказов самой ходилки."""
import subprocess
import time

ПИТОН = r"C:\Program Files\Python311\python.exe"
П = r"C:\sender\_ops\checko_finansy.py"

subprocess.run(["powershell", "-NoProfile", "-Command",
                "Get-CimInstance Win32_Process | Where-Object { "
                "$_.CommandLine -like '*checko_finansy*' } | ForEach-Object { "
                "Stop-Process -Id $_.ProcessId -Force }"],
               capture_output=True, text=True, timeout=60)
time.sleep(3)

t0 = time.time()
try:
    r = subprocess.run([ПИТОН, П, "--lim", "2", "--potok", "1", "--mobilnye",
                        "--bez-bazy"],
                       capture_output=True, text=True, timeout=420,
                       encoding="utf-8", errors="replace")
    вых, ош, код = r.stdout, r.stderr, r.returncode
except subprocess.TimeoutExpired as ex:
    вых = (ex.stdout or b"").decode("utf-8", "replace") if isinstance(
        ex.stdout, bytes) else (ex.stdout or "")
    ош = (ex.stderr or b"").decode("utf-8", "replace") if isinstance(
        ex.stderr, bytes) else (ex.stderr or "")
    код = "таймаут 420 с"

print("=" * 78)
print("=== СВОДКА: ДВЕ КОМПАНИИ В ОДИН ПОТОК ===")
print("код возврата: %s, время %.0f с" % (код, time.time() - t0))
print("")
print("--- вывод ходилки ---")
for с in (вых or "(пусто)").splitlines():
    print("   " + с[:170])
if ош:
    print("--- ошибки ---")
    for с in ош.splitlines()[-10:]:
        print("   " + с[:170])
