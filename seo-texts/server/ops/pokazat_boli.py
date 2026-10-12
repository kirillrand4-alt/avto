# -*- coding: utf-8 -*-
"""Показать живые тексты болей Meyer — что уже написано, а чего нет."""
import sys
sys.path.insert(0, r"C:\sender")
from sender import ai_letter                                     # noqa: E402

pains = ai_letter._okved_pains()
for раздел in ("meyer_foto", "meyer_rentgen", "meyer"):
    т = pains.get(раздел) or {}
    print("=== %s (%d) ===" % (раздел, len(т)))
    for к in sorted(т):
        print("   %-8s %s" % (к, т[к]))
    print("")
print("=== _по_умолчанию ===")
for к, v in (pains.get("_по_умолчанию") or {}).items():
    print("   %-16s %s" % (к, v))
print("")
print("=== есть ли отраслевой слой ===")
print("   разделы: %s" % ", ".join(sorted(pains)))
print("   ключ по названию отрасли: %s"
      % ("ЕСТЬ" if any("отрасл" in k for k in pains) else "НЕТ"))
