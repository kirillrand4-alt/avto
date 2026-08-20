# -*- coding: utf-8 -*-
"""Хвост САМОГО СВЕЖЕГО лога отцеплённой партии.

Отцеплённый прогон пишет stdout в C:\\sender\\_ops\\partiya_gen-<метка>.log,
потому что stdout задания панели ему не достаётся. Имя с меткой времени
заранее неизвестно - находим по времени изменения.
"""
import glob
import io
import os
import sys

сколько = int(sys.argv[1]) if len(sys.argv) > 1 else 40
файлы = sorted(glob.glob(r"C:\sender\_ops\partiya_gen-*.log")
               + glob.glob(r"C:\sender\_ops\partiya_gen-*.err"),
               key=os.path.getmtime, reverse=True)
if not файлы:
    print("логов отцеплённых партий нет")
    raise SystemExit(0)
for путь in файлы[:2]:
    раз = os.path.getsize(путь)
    print(f"=== {os.path.basename(путь)}: {раз} байт, изменён "
          f"{int(os.path.getmtime(путь))}")
    if not раз:
        print("  (пусто)")
        continue
    with io.open(путь, encoding="utf-8", errors="replace") as f:
        строки = f.readlines()
    print("".join(строки[-сколько:]))
