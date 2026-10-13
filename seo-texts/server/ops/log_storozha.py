# -*- coding: utf-8 -*-
"""Ищем в логах службы строки про ящик (ошибки опроса IMAP).

    log_storozha.py <кусок> [n=30]
"""
import glob
import io
import os
import sys
К = sys.argv[1]
N = int(dict(а.split("=", 1) for а in sys.argv[2:] if "=" in а).get("n", "30"))
файлы = []
for маска in (r"C:\sender\*.log", r"C:\sender\logs\*.log*", r"C:\sender\log\*.log*", r"C:\sender\*.err*", r"C:\sender\*.out*",
              r"C:\sender\service\*.log*"):
    файлы += glob.glob(маска)
файлы = sorted(set(файлы), key=os.path.getmtime)[-8:]
for ф in файлы:
    print("файл %s (%d КБ, изм. %s)" % (ф, os.path.getsize(ф) // 1024, __import__("time").ctime(os.path.getmtime(ф))))
for ф in файлы:
    try:
        стр = [с for с in io.open(ф, encoding="utf-8", errors="replace") if К in с]
    except Exception:  # noqa: BLE001
        continue
    if стр:
        print("--- %s: %d строк" % (ф, len(стр)))
        for с in стр[-N:]:
            print("  " + с.rstrip()[:240])
print("=== ЛОГ СТОРОЖА ===")
