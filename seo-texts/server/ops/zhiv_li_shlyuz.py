# -*- coding: utf-8 -*-
"""Отвечает ли шлюз и на каких моделях. Плюс полный текст ошибок блока."""
import glob
import io
import os
import sys
import time
from collections import Counter

sys.path.insert(0, r"C:\sender")

п = sorted(glob.glob(r"C:\sender\_ops\partiya_gen-*.err"),
           key=os.path.getmtime, reverse=True)[0]
т = io.open(п, encoding="utf-8", errors="replace").read()
print("=== ОШИБКИ БЛОКА (%d Б) ===" % len(т))
причины = Counter()
for с in т.splitlines():
    с = с.strip()
    if "RuntimeError" in с or "стрим молчит" in с or "Error" in с:
        причины[с[:120]] += 1
for c, n in причины.most_common(6):
    print("   %3d  %s" % (n, c))

print("\n=== ПРОБНЫЕ ВЫЗОВЫ ===")
from sender.review_lenses import default_caller                # noqa: E402
for модель in ("claude-sonnet-4-6", "claude-opus-4-8", "claude-opus-4-7",
               "claude-haiku-4-5"):
    т0 = time.time()
    try:
        текст, факт = default_caller("Ответь одним словом: готов",
                                     max_tokens=16, model=модель)
        print("   %-22s ОК за %5.1f с, модель ответа %s, ответ %r"
              % (модель, time.time() - т0, факт, str(текст)[:40]))
    except Exception as e:                                     # noqa: BLE001
        print("   %-22s ОШИБКА за %5.1f с: %s"
              % (модель, time.time() - т0, str(e)[:110]))
