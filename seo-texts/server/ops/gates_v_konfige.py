# -*- coding: utf-8 -*-
"""Секция gates в sender.yaml: что там сейчас. Печатаем ТОЛЬКО её."""
import io, re
П = r"C:\sender\sender.yaml"
т = io.open(П, encoding="utf-8", errors="replace").read()
строки = т.splitlines()
внутри = False
печать = []
for i, с in enumerate(строки):
    if re.match(r"^gates\s*:", с):
        внутри = True
        печать.append((i + 1, с))
        continue
    if внутри:
        if с.strip() and not с.startswith((" ", "\t")):
            break
        печать.append((i + 1, с))
print("=" * 70)
print("=== СЕКЦИЯ gates В sender.yaml ===")
if not печать:
    print("секции gates нет вовсе")
for n, с in печать:
    print("   %4d| %s" % (n, с))
print("")
print("строк в файле: %d" % len(строки))
for ключ in ("otkaz_stop_yashchik", "otkaz_stop_napravlenie",
             "otkaz_min_yashchikov"):
    print("   %-24s %s" % (ключ, "есть" if ключ in т else "НЕТ (берётся умолчание)"))
