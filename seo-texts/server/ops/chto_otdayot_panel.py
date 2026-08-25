# -*- coding: utf-8 -*-
"""Какой бандл панель реально отдаёт браузеру.

Лента после перезапуска осталась старой. Значит либо служба берёт статику
не из того каталога, куда я собрал, либо браузер держит старый файл.
Проверяем оба конца: что лежит в известных dist и что отдаёт сама панель.
"""
import glob
import io
import os
import re
import subprocess

print("=== КАТАЛОГИ dist ПОД C:\\sender ===")
for п in glob.glob(r"C:\sender\**\dist\index.html", recursive=True):
    if "node_modules" in п:
        continue
    т = io.open(п, encoding="utf-8", errors="replace").read()
    ссылки = re.findall(r'(?:src|href)="([^"]+)"', т)
    print("   %s  (изменён %s)"
          % (п, __import__("time").strftime(
              "%d.%m %H:%M", __import__("time").localtime(os.path.getmtime(п)))))
    for с in ссылки:
        print("      -> %s" % с)

print("\n=== ЧТО ОТДАЁТ САМА ПАНЕЛЬ ===")
for адрес in ("http://127.0.0.1:8000/", "http://127.0.0.1/", "http://localhost:8000/"):
    try:
        import urllib.request
        with urllib.request.urlopen(адрес, timeout=6) as о:
            т = о.read(4000).decode("utf-8", "replace")
        print("   %s -> %d байт" % (адрес, len(т)))
        for с in re.findall(r'(?:src|href)="([^"]+)"', т):
            print("      -> %s" % с)
        break
    except Exception as e:  # noqa: BLE001
        print("   %s: %s" % (адрес, str(e)[:60]))

print("\n=== КОМАНДА СЛУЖБЫ SenderPanel ===")
try:
    в = subprocess.run(["sc", "qc", "SenderPanel"], capture_output=True,
                       text=True, timeout=20)
    for с in (в.stdout or "").splitlines():
        if any(к in с.upper() for к in ("BINARY", "PATH")):
            print("   %s" % с.strip())
except Exception as e:  # noqa: BLE001
    print("   sc не дался: %s" % str(e)[:60])
for имя in ("start_panel.ps1", "run_panel.py", "panel.py", "serve.py"):
    for п in glob.glob(r"C:\sender\**\%s" % имя, recursive=True):
        if "node_modules" in п:
            continue
        т = io.open(п, encoding="utf-8", errors="replace").read()
        for с in т.splitlines():
            if "static" in с.lower() or "dist" in с.lower():
                print("   %s | %s" % (os.path.basename(п), с.strip()[:100]))
