# -*- coding: utf-8 -*-
"""Что у зенки в очереди и сколько осталось ходилке. Сводка в конце."""
import io
import os
import subprocess
import time

ZENNO = r"C:\seostat\drop\zenno"
ФАЙЛЫ = {"ochered.txt": "очередь для зенки",
         "otdano.txt": "уже отдавали",
         "ne_otkrylis.txt": "не открылись"}
ПИТОН = r"C:\Program Files\Python311\python.exe"

стат = subprocess.run([ПИТОН, r"C:\sender\server\zenno_most.py", "--stat"],
                      capture_output=True, text=True, timeout=300,
                      encoding="utf-8", errors="replace")

размеры = []
for имя, что in ФАЙЛЫ.items():
    п = os.path.join(ZENNO, имя)
    if os.path.exists(п):
        n = sum(1 for с in io.open(п, encoding="utf-8", errors="replace")
                if с.strip())
        размеры.append("%-18s %-16s %7d строк  изменён %s"
                       % (имя, что, n,
                          time.strftime("%d.%m %H:%M",
                                        time.localtime(os.path.getmtime(п)))))
    else:
        размеры.append("%-18s %-16s НЕТ" % (имя, что))

for кат, что in (("gotovo", "готово от зенки"), ("razobrano", "разобрано")):
    п = os.path.join(ZENNO, кат)
    n = len(os.listdir(п)) if os.path.isdir(п) else 0
    размеры.append("%-18s %-16s %7d файлов" % (кат + "\\", что, n))

# первые строки очереди — какого вида задания
образцы = []
п = os.path.join(ZENNO, "ochered.txt")
if os.path.exists(п):
    for i, с in enumerate(io.open(п, encoding="utf-8", errors="replace")):
        if с.strip():
            образцы.append(с.strip()[:90])
        if len(образцы) >= 4:
            break

демон = subprocess.run(
    ["powershell", "-NoProfile", "-Command",
     "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like "
     "'*zenno_most*' } | ForEach-Object { $м = [int]((New-TimeSpan -Start "
     "$_.CreationDate -End (Get-Date)).TotalMinutes); \"PID $($_.ProcessId) "
     "$м мин\" }"],
    capture_output=True, text=True, timeout=90).stdout.strip()

print("=" * 76)
print("=== СВОДКА: ЗЕНКА ===")
print("демон zenno_most: %s" % (демон or "НЕ ЗАПУЩЕН"))
print("")
for с in размеры:
    print("   " + с)
print("")
print("вид заданий в очереди:")
for с in (образцы or ["   очередь пуста"]):
    print("   " + с)
print("")
print("--- вывод zenno_most --stat ---")
for с in (стат.stdout or "(пусто)").splitlines()[-14:]:
    print("   " + с[:150])
if стат.stderr:
    for с in стат.stderr.splitlines()[-4:]:
        print("   ош: " + с[:150])
