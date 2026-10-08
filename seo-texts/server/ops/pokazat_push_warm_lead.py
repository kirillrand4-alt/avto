# -*- coding: utf-8 -*-
"""Показать push_warm_lead на сервере целиком: он ушёл вперёд репозитория."""
import io

ФАЙЛ = r"C:\sender\sender\leaddesk.py"
строки = io.open(ФАЙЛ, encoding="utf-8").read().splitlines()
начало = конец = None
for н, с in enumerate(строки):
    if "def push_warm_lead" in с:
        начало = н
    elif начало is not None and с.lstrip().startswith(("def ", "@staticmethod",
                                                       "@classmethod")) and н > начало:
        конец = н
        break
конец = конец or min(len(строки), (начало or 0) + 120)
for i in range(начало, конец):
    print("   %4d | %s" % (i + 1, строки[i][:120]))
print("")
print("=" * 74)
print("=== push_warm_lead НА СЕРВЕРЕ (строки %d-%d) ===" % (начало + 1, конец))
