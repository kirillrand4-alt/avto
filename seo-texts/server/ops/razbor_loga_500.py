# -*- coding: utf-8 -*-
"""Разбор лога генерации 500: сколько сбоев и каких, жив ли работник."""
import io
import os
import re
import subprocess
import time
from collections import Counter

т = io.open(r"C:\sender\_ops\gen500.log", encoding="utf-8", errors="replace").read()
строки = т.splitlines()
print("строк в логе: %d, размер %d" % (len(строки), len(т)))
вид = Counter()
for с in строки:
    if "10054" in с:
        вид["обрыв соединения 10054"] += 1
    elif "ретрай" in с or "retry" in с.lower():
        вид["ретрай (другое)"] += 1
    elif "Traceback" in с:
        вид["Traceback"] += 1
    elif re.search(r"(?i)error|ошибк|сбой", с):
        вид["прочие ошибки"] += 1
    else:
        вид["прочее"] += 1
for к, n in вид.most_common():
    print("   %-26s %6d" % (к, n))
print("")
прочее = [с for с in строки if not re.search(r"10054|ретрай", с)]
print("--- последние строки, кроме обрывов ---")
for с in прочее[-14:]:
    print("   " + с[:200])
pid = io.open(r"C:\sender\_ops\gen500.pid").read().strip()
вывод = subprocess.run(["tasklist", "/FI", "PID eq %s" % pid],
                       capture_output=True, text=True).stdout
print("")
print("работник %s жив: %s" % (pid, pid in вывод))
м = os.path.getmtime(r"C:\sender\_ops\gen500.log")
print("лог обновлялся %d с назад" % (time.time() - м))
print("=== ЛОГ 500 ===")
