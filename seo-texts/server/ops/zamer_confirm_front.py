# -*- coding: utf-8 -*-
"""Диагностика: положить на дроп Confirm.tsx/Layout.tsx фронта панели (только чтение)."""
import os
import shutil
for п, _д, фф in os.walk(r"C:\sender\sender\web\src"):
    if ".bak" in п or "node_modules" in п:
        continue
    for ф in фф:
        if ф in ("Confirm.tsx", "Layout.tsx"):
            shutil.copy2(os.path.join(п, ф),
                         r"C:\seostat\drop\drop-storage" + "\\srv_front_" + ф)
            print("на дропе: srv_front_" + ф, os.path.join(п, ф)[len(r"C:\sender\sender"):])
print("=== ГОТОВО ===")
