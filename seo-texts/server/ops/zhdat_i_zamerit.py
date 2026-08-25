# -*- coding: utf-8 -*-
"""Подождать, пока прогон наберёт N попыток, и показать долю брака."""
import glob
import io
import os
import re
import sys
import time

НУЖНО = int(sys.argv[1]) if len(sys.argv) > 1 else 50
ЖДАТЬ = float(sys.argv[2]) if len(sys.argv) > 2 else 600.0
СТРОКА = re.compile(r"\[(\d+)/(\d+)\]\s+(ОК|брак)\s+(\S+)\s+(.*?)\s+(\d+)с\s+\$(\d+\.\d+)"
                    r"(?:\s*\|\s*(.*))?")

логи = sorted(glob.glob(r"C:\sender\_ops\partiya_gen-*.log"), key=os.path.getmtime)
п = логи[-1]
print("смотрим %s" % os.path.basename(п))
край = time.time() + ЖДАТЬ
while time.time() < край:
    т = io.open(п, encoding="utf-8", errors="replace").read()
    строки = [м for м in СТРОКА.finditer(т)]
    if len(строки) >= НУЖНО:
        break
    time.sleep(20)
т = io.open(п, encoding="utf-8", errors="replace").read()
ок = брак = 0
деньги = 0.0
причины = {}
for м in СТРОКА.finditer(т):
    деньги += float(м.group(7))
    if м.group(3) == "ОК":
        ок += 1
    else:
        брак += 1
        пр = (м.group(8) or "")[:60]
        ключ = "нет JSON" if "нет JSON" in пр else пр.split(":")[0][:40]
        причины[ключ] = причины.get(ключ, 0) + 1
всего = ок + брак
print("попыток %d: ок %d, брак %d (%.0f%%), потрачено $%.2f, $%.3f за готовое"
      % (всего, ок, брак, 100.0 * брак / всего if всего else 0, деньги,
         деньги / ок if ок else 0))
for пр, n in sorted(причины.items(), key=lambda x: -x[1])[:8]:
    print("   %-42s %d" % (пр, n))
