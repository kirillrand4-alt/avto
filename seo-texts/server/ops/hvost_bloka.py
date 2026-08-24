# -*- coding: utf-8 -*-
"""Хвост лога текущего блока очереди и отчёт драйвера."""
import glob
import io
import json
import os
import time

for п in sorted(glob.glob(r"C:\sender\_ops\ochered-blok*.log"),
                key=lambda x: -os.path.getmtime(x))[:2]:
    print("=== %s (обновлён %.1f мин назад, %d байт) ==="
          % (os.path.basename(п), (time.time() - os.path.getmtime(п)) / 60.0,
             os.path.getsize(п)))
    строки = io.open(п, encoding="utf-8", errors="replace").readlines()
    for с in строки[-30:]:
        print("  %s" % с.rstrip()[:180])

п = r"C:\sender\_ops\ochered-vladeltsa.jsonl"
if os.path.exists(п):
    print("\n=== ОТЧЁТ ДРАЙВЕРА ===")
    for с in io.open(п, encoding="utf-8"):
        с = с.strip()
        if с:
            print("  %s" % json.dumps(json.loads(с), ensure_ascii=False)[:180])
