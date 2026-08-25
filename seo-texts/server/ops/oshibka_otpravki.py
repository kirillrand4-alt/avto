# -*- coding: utf-8 -*-
"""Полная трассировка падения автоотправки."""
import io
import os
import time

п = r"C:\sender\_ops\panel_err.log"
строки = io.open(п, encoding="utf-8", errors="replace").readlines()
print("журнал ошибок: %d строк, обновлён %.1f мин назад"
      % (len(строки), (time.time() - os.path.getmtime(п)) / 60.0))

# последний блок трассировки про auto_send
последний = None
for i in range(len(строки) - 1, max(0, len(строки) - 4000), -1):
    if "auto_send" in строки[i]:
        последний = i
        break
if последний is None:
    print("строк про auto_send нет")
else:
    начало = max(0, последний - 4)
    print("\n=== ХВОСТ ВОКРУГ ПОСЛЕДНЕЙ ОШИБКИ ===")
    for с in строки[начало:последний + 30]:
        print("  " + с.rstrip()[:200])

print("\n=== ПОСЛЕДНИЕ 25 СТРОК ЖУРНАЛА ===")
for с in строки[-25:]:
    print("  " + с.rstrip()[:200])
