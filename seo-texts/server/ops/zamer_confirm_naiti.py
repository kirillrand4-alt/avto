# -*- coding: utf-8 -*-
"""Диагностика «Подтвердить отправку»: найти файлы с ручкой /confirm/queue и
скопировать их на дроп для чтения (только чтение кода, ничего не меняет)."""
import io
import os
import shutil
корень = r"C:\sender\sender"
for п, _д, фф in os.walk(корень):
    if "node_modules" in п or "dist" in п:
        continue
    for ф in фф:
        if not ф.endswith((".py", ".tsx", ".ts")):
            continue
        путь = os.path.join(п, ф)
        try:
            т = io.open(путь, encoding="utf-8", errors="replace").read()
        except Exception:
            continue
        if "confirm/queue" in т:
            отн = os.path.relpath(путь, корень).replace("\\", "_").replace("/", "_")
            shutil.copy2(путь, r"C:\seostat\drop\drop-storage" + "\\" + "srv_" + отн)
            print("на дропе: srv_" + отн, os.path.getsize(путь), "байт")
print("=== ГОТОВО ===")
