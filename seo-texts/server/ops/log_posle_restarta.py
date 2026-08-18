# -*- coding: utf-8 -*-
"""Что панель написала в лог ПОСЛЕ перезапуска: поднялись ли фоновые циклы."""
import io
import os

for путь in (r"C:\sender\_ops\panel_err.log", r"C:\sender\_ops\panel_out.log"):
    р = os.path.getsize(путь)
    with io.open(путь, "rb") as f:
        f.seek(max(0, р - 200_000))
        текст = f.read().decode("utf-8", "replace")
    строки = [s for s in текст.splitlines() if s.strip()]
    # Старт uvicorn/панели — граница между «до» и «после»
    метки = [i for i, s in enumerate(строки)
             if "Started server process" in s or "Application startup" in s
             or "Uvicorn running" in s]
    начало = метки[-1] if метки else max(0, len(строки) - 60)
    print(f"\n=== {os.path.basename(путь)}: строк после старта "
          f"{len(строки) - начало}")
    for s in строки[начало:начало + 60]:
        print("  " + s[:170])
