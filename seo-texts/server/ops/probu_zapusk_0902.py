# -*- coding: utf-8 -*-
"""Только чтение: как заказать пробу адресов у VPS."""
import inspect
import io
import re
import sys

sys.path.insert(0, r"C:\sender")
import sender.probe_sync as PS  # noqa: E402

print("=== ПУБЛИЧНЫЕ ФУНКЦИИ probe_sync ===")
for имя in sorted(dir(PS)):
    о = getattr(PS, имя)
    if callable(о) and not имя.startswith("_"):
        try:
            print("  %-30s %s" % (имя, str(inspect.signature(о))[:110]))
        except Exception:
            print("  %-30s (класс)" % имя)

т = io.open(r"C:\sender\sender\probe_sync.py", encoding="utf-8",
            errors="replace").read()
лн = т.splitlines()
print("\n=== ГДЕ ФОРМИРУЕТСЯ ЗАДАНИЕ РАБОТНИКУ ===")
for м in re.finditer(r"(def \w+|vjob-|probe-zadanie|ЗАДАЧА|publikaciya|опублик)", т):
    н = т[:м.start()].count("\n")
    с = лн[н].strip()
    if с.startswith("#"):
        continue
    print("  %4d| %s" % (н + 1, с[:100]))
