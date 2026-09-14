# -*- coding: utf-8 -*-
"""Где в sender.yaml упомянуты компрессорные домены — до единой строки."""
import io
import re

ФАЙЛ = r"C:\sender\sender.yaml"
ДОМЕНЫ = ("kompressor-air-trade.ru", "kompressor-pro-expert.ru",
          "compressor-air-expert.ru", "kompressor-pro-trade.ru",
          "kompressor-air-expert.ru", "kompressor-expert.ru",
          "compressor-store.ru")

т = io.open(ФАЙЛ, encoding="utf-8").read()
строки = т.splitlines()
print("файл: %d строк, %d байт" % (len(строки), len(т)))
раздел = ""
попадания = []
for н, с in enumerate(строки, 1):
    if re.match(r"^[A-Za-zА-Яа-я_]", с):
        раздел = с.split(":")[0]
    if any(д in с for д in ДОМЕНЫ):
        попадания.append((н, раздел, с))
print("строк с компрессорными доменами: %d" % len(попадания))
разделы = {}
for н, р, с in попадания:
    разделы.setdefault(р, []).append((н, с))
for р, сп in разделы.items():
    print("")
    print("--- раздел «%s»: %d строк ---" % (р, len(сп)))
    for н, с in сп[:70]:
        print("   %5d | %s" % (н, с[:110]))

print("")
print("--- как выглядит один блок ящика (для якорей) ---")
if попадания:
    н0 = попадания[0][0]
    for н in range(max(1, н0 - 6), min(len(строки), н0 + 10)):
        print("   %5d | %s" % (н, строки[н - 1][:110]))
print("")
print("=" * 74)
print("=== ГДЕ ЖИВУТ КОМПРЕССОРНЫЕ ЯЩИКИ В КОНФИГЕ ===")
