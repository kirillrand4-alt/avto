# -*- coding: utf-8 -*-
"""Идут ли письма в ночном блоке и по какой цене."""
import glob
import io
import os
import re
import time
from collections import Counter

п = sorted(glob.glob(r"C:\sender\_ops\partiya_gen-*.log"),
           key=os.path.getmtime, reverse=True)[0]
с = io.open(п, encoding="utf-8", errors="replace").read().splitlines()
письма = [x for x in с if re.match(r"\s*\[\d+/\d+\]", x)]
print("лог %s: %d строк, писем %d, изменён %.1f мин назад"
      % (os.path.basename(п), len(с), len(письма),
         (time.time() - os.path.getmtime(п)) / 60))
for x in письма[-12:]:
    print("   %s" % x.strip()[:150])

цены, секунды = [], []
for x in письма:
    m = re.search(r"(\d+)с\s+\$([\d.]+)", x)
    if m:
        секунды.append(int(m.group(1)))
        цены.append(float(m.group(2)))
if цены:
    цены_с = sorted(цены)
    сек_с = sorted(секунды)
    ок = sum(1 for x in письма if " ОК " in x)
    print("\nписем ОК: %d из %d (%.0f%%)" % (ок, len(письма),
                                             100.0 * ок / len(письма)))
    print("цена попытки: медиана $%.3f, среднее $%.3f, максимум $%.3f"
          % (цены_с[len(цены_с) // 2], sum(цены) / len(цены), цены_с[-1]))
    print("время на письмо: медиана %d с, максимум %d с"
          % (сек_с[len(сек_с) // 2], сек_с[-1]))
    print("суммарно потрачено в блоке: $%.2f" % sum(цены))

шум = Counter()
for x in с:
    if "предклассификатор" in x:
        шум["предклассификатор не сработал"] += 1
    if "линза" in x and "не получила" in x:
        шум["линза не ответила"] += 1
print("\nсбои: %s" % dict(шум))
