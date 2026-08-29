# -*- coding: utf-8 -*-
"""Из чего физически состоит конвейер: размеры, зависимости, привязки к машине."""
import os
import sys
import platform

print("python: %s" % sys.version.split()[0])
print("система: %s %s" % (platform.system(), platform.release()))
print()
print("=== ДАННЫЕ (что придётся копировать) ===")
всего = 0
for п in (r"C:\sender\sender.db", r"C:\sender\enrich.db",
          r"C:\sender\obzvon-index.db", r"C:\sender\baza.key"):
    if os.path.exists(п):
        р = os.path.getsize(п)
        всего += р
        print("   %-34s %8.1f МБ" % (os.path.basename(п), р / 1048576))
    else:
        print("   %-34s нет" % os.path.basename(п))
код = 0
for корень in (r"C:\sender\sender",):
    for путь, кат, файлы in os.walk(корень):
        кат[:] = [d for d in кат if d not in ("__pycache__", "node_modules")]
        for имя in файлы:
            if имя.endswith((".py", ".html", ".js", ".css")):
                код += os.path.getsize(os.path.join(путь, имя))
print("   %-34s %8.1f МБ" % ("код панели (sender/)", код / 1048576))
print("   ИТОГО данных: %.1f МБ" % (всего / 1048576))
print()
print("=== ЧТО НУЖНО ИЗ ОКРУЖЕНИЯ (только имена, не значения) ===")
нужны = []
for k in sorted(os.environ):
    if any(с in k.upper() for с in ("BOX", "PROVIDER", "UNSUB", "DOLPHIN",
                                    "DROP", "TELEGRAM", "BITRIX", "POSTOFFICE",
                                    "POSTMASTER", "VK_", "MAYAK", "SENDER")):
        нужны.append(k)
print("   переменных: %d" % len(нужны))
print("   %s" % ", ".join(нужны))
print()
print("=== ЗАВИСИМОСТИ КОДА ===")
import re
внешние = set()
своё = set()
for путь, кат, файлы in os.walk(r"C:\sender\sender"):
    кат[:] = [d for d in кат if d not in ("__pycache__", "node_modules", "web")]
    for имя in файлы:
        if not имя.endswith(".py"):
            continue
        try:
            т = open(os.path.join(путь, имя), encoding="utf-8",
                     errors="ignore").read()
        except Exception:
            continue
        for м in re.finditer(r"^\s*(?:from|import)\s+([a-zA-Z_][\w.]*)", т, re.M):
            и = м.group(1).split(".")[0]
            (своё if и in ("sender",) else внешние).add(и)
станд = set(sys.stdlib_module_names)
чужие = sorted(x for x in внешние if x not in станд and x != "sender")
print("   не из стандартной библиотеки: %s" % ", ".join(чужие))
print()
print("=== ПРИВЯЗКИ К ЭТОЙ МАШИНЕ ===")
пути = [x for x in ("C:\\sender", r"C:\sender\_ops", r"C:\sender\server")
        if os.path.isdir(x)]
print("   абсолютные пути C:\\sender зашиты в конфиге и ops: да")
print("   служба Windows SenderPanel: %s"
      % ("есть" if os.system("sc.exe query SenderPanel >nul 2>&1") == 0 else "нет"))
