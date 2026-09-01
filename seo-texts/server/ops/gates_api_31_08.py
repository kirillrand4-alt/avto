# -*- coding: utf-8 -*-
"""Только чтение: API гейтов для паузы домена."""
import inspect
import io
import re
import sys

стр = io.open(r"C:\sender\sender\gates.py", encoding="utf-8",
              errors="replace").read().splitlines()
for имя in ("_pause_domain", "def pause", "def manual"):
    н = [i for i, x in enumerate(стр) if re.search(r"def .*%s" % имя.replace("def ", ""), x)]
    for i in н[:2]:
        print("=== gates.py:%d ===" % (i + 1))
        for j in range(i, min(i + 22, len(стр))):
            print("  %4d  %s" % (j + 1, стр[j][:108]))
        print()

sys.path.insert(0, r"C:\sender")
import sender.gates as G  # noqa: E402
print("=== публичные методы классов gates ===")
for имя in dir(G):
    o = getattr(G, имя)
    if inspect.isclass(o) and not имя.endswith("Error"):
        м = [m for m in dir(o) if not m.startswith("__")
             and ("pause" in m or "manual" in m or "domain" in m or "check" in m)]
        if м:
            print("  %s: %s" % (имя, м))
            for m in м:
                try:
                    print("     %-22s %s" % (m, str(inspect.signature(getattr(o, m)))[:100]))
                except Exception:
                    pass
