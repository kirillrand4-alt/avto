# -*- coding: utf-8 -*-
"""Только чтение: свежий лог прогона партии. Итог печатаю ПОСЛЕДНИМ (§8.10)."""
import glob
import os
import datetime
import io

логи = sorted(glob.glob(r"C:\sender\_ops\partiya_gen-*.log"),
              key=os.path.getmtime, reverse=True)
if not логи:
    print("логов нет")
    raise SystemExit(0)
л = логи[0]
т = datetime.datetime.fromtimestamp(os.path.getmtime(л))
стр = io.open(л, encoding="utf-8", errors="replace").read().splitlines()
print("=== %s ===" % os.path.basename(л))
print("  изменён %s, строк %d, байт %d"
      % (т.strftime("%H:%M:%S"), len(стр), os.path.getsize(л)))
print("\n=== ПЕРВЫЕ 14 СТРОК (проверка, как понят запуск) ===")
for x in стр[:14]:
    print("  " + x[:150])
print("\n=== ПОСЛЕДНИЕ 22 СТРОКИ ===")
for x in стр[-22:]:
    print("  " + x[:150])
ок = sum(1 for x in стр if " ОК " in x or x.strip().startswith("[") and " ОК" in x)
брак = sum(1 for x in стр if "брак" in x.lower())
print("\n=== ИТОГ ===")
print("  строк с ОК: %d | со словом брак: %d" % (ок, брак))
print("  сейчас на сервере: %s" % datetime.datetime.now().strftime("%H:%M:%S"))
