# -*- coding: utf-8 -*-
"""Только чтение: store.increment_sent и append_event — что делают без строки."""
import io
import re

стр = io.open(r"C:\sender\sender\store.py", encoding="utf-8",
              errors="replace").read().splitlines()
for имя in ("increment_sent", "append_event"):
    н = [i for i, x in enumerate(стр) if re.match(r"\s*def %s" % имя, x)]
    for i in н:
        print("=== store.py: %s (строка %d) ===" % (имя, i + 1))
        отступ = len(стр[i]) - len(стр[i].lstrip())
        for j in range(i, min(i + 44, len(стр))):
            x = стр[j]
            if j > i and x.strip() and (len(x) - len(x.lstrip())) <= отступ \
                    and x.lstrip().startswith("def "):
                break
            print("  %4d  %s" % (j + 1, x[:110]))
        print()
