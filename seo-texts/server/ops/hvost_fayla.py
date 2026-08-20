# -*- coding: utf-8 -*-
"""Хвост любого файла на сервере: hvost_fayla.py <путь> [строк]."""
import io
import os
import sys

путь = sys.argv[1]
сколько = int(sys.argv[2]) if len(sys.argv) > 2 else 40
if not os.path.exists(путь):
    print(f"нет файла: {путь}")
    raise SystemExit(0)
print(f"{путь}: {os.path.getsize(путь)} байт")
with io.open(путь, encoding="utf-8", errors="replace") as f:
    строки = f.readlines()
print("".join(строки[-сколько:]))
