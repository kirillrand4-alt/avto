# -*- coding: utf-8 -*-
"""Что делает sverka_prigovorov: описание, шаги, куда пишет, как долго."""
import io
import os
import re
import time

П = r"C:\sender\server\ops\sverka_prigovorov.py"
ЦМД = r"C:\sender\_ops\sverka-prigovorov.cmd"

if not os.path.exists(П):
    print("нет файла %s" % П)
    raise SystemExit(0)

т = io.open(П, encoding="utf-8", errors="replace").read()
стр = т.splitlines()

print("=== %s: %d строк, %d байт, изменён %s ==="
      % (os.path.basename(П), len(стр), len(т),
         time.strftime("%d.%m.%Y %H:%M", time.localtime(os.path.getmtime(П)))))
print("")
print("=== ОПИСАНИЕ (шапка) ===")
м = re.search(r'"""(.*?)"""', т, re.S)
print(м.group(1).strip()[:3000] if м else "шапки нет")

print("")
print("=== ФУНКЦИИ ===")
for м in re.finditer(r"^def\s+([a-zA-Zа-яА-Я0-9_]+)\(([^)]{0,70})", т, re.M):
    print("   %s(%s)" % (м.group(1), м.group(2)[:60]))

print("")
print("=== КУДА ПИШЕТ (UPDATE/INSERT/DELETE) ===")
видели = set()
for i, с in enumerate(стр):
    м = re.search(r"(UPDATE|INSERT INTO|INSERT OR \w+ INTO|DELETE FROM)\s+"
                  r"([a-zA-Z_]+)", с)
    if м:
        ключ = (м.group(1).split()[0], м.group(2))
        if ключ not in видели:
            видели.add(ключ)
            print("%5d| %s" % (i + 1, с.strip()[:120]))

print("")
print("=== БАЗЫ И ВНЕШНИЕ АДРЕСА ===")
for п in sorted(set(re.findall(r"r?['\"](C:\\[^'\"]+\.db)['\"]", т))):
    print("   %s" % п)
for п in sorted(set(re.findall(r"['\"](https?://[^'\"]{0,70})['\"]", т)))[:6]:
    print("   %s" % п)

print("")
print("=== ЧЕМ ЗАПУСКАЕТСЯ ===")
if os.path.exists(ЦМД):
    print(io.open(ЦМД, encoding="utf-8", errors="replace").read()[:600])
else:
    print("   %s не найден" % ЦМД)
