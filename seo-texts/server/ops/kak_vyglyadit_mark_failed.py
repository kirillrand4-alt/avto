# -*- coding: utf-8 -*-
"""Как выглядит mark_failed в боевом store.py — печать функции как есть.

Патч не применился: якорь сигнатуры не нашёлся ни разу. Значит на сервере
она другой формы, и гадать нельзя — печатаем первые строки функции
дословно, вместе с номерами, чтобы построить точный якорь.
"""
import io

путь = r"C:\sender\sender\store.py"
строки = io.open(путь, encoding="utf-8").read().splitlines()

начала = [н for н, с in enumerate(строки) if "def mark_failed" in с]
print("вхождений «def mark_failed»: %d" % len(начала))
for н in начала:
    print("\n--- строка %d ---" % (н + 1))
    for к in range(н, min(н + 26, len(строки))):
        print("%5d| %s" % (к + 1, строки[к]))

print("\n=== вызовы mark_failed по файлу ===")
for н, с in enumerate(строки):
    if "mark_failed" in с and "def " not in с:
        print("%5d| %s" % (н + 1, с.strip()[:110]))
