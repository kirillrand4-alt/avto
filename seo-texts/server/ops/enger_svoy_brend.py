# -*- coding: utf-8 -*-
"""ai_letter: канон КЦ 14.10 — представление первой строкой, фраза о компании (6000 проектов,
МКС, Enger, 20 брендов, винтовые и выше), без «Смотрел профиль». Правка по якорям."""
import io
import py_compile
import shutil
import sys
import time
ПУТЬ = r"C:\\sender\\sender\\ai_letter.py"
т = io.open(ПУТЬ, encoding="utf-8").read()
if "СОБСТВЕННЫЙ бренд Компрессор Центра" in т:
    print("=== ENGER СВОЙ БРЕНД: УЖЕ БЫЛО ===")
    sys.exit(0)
ПАРЫ = [("    'fiac', 'remeza', 'enger', 'cross air', 'hansmann', 'berg',\n)", "    'fiac', 'remeza', 'cross air', 'hansmann', 'berg',\n)\n# Enger — СОБСТВЕННЫЙ бренд Компрессор Центра (владелец 14.10, фраза о\n# компании в каноне КЦ), его из списка чужих марок убрали."), ("    'энгер', 'кросс эйр', 'хансманн', 'гарднер денвер',\n)", "    'кросс эйр', 'хансманн', 'гарднер денвер',\n)")]
for с, _н in ПАРЫ:
    if т.count(с) != 1:
        print("якорь (%d): %r" % (т.count(с), с[:120]))
        print("=== ENGER СВОЙ БРЕНД: НЕ ПРИМЕНЕНО ===")
        sys.exit(0)
бэкап = ПУТЬ + ".bak-%d" % int(time.time())
shutil.copy2(ПУТЬ, бэкап)
for с, н in ПАРЫ:
    т = т.replace(с, н)
io.open(ПУТЬ, "w", encoding="utf-8").write(т)
try:
    py_compile.compile(ПУТЬ, doraise=True)
except Exception as е:  # noqa: BLE001
    shutil.copy2(бэкап, ПУТЬ)
    print("сбой, откат: %s" % е)
    print("=== ENGER СВОЙ БРЕНД: ОТКАТ ===")
    sys.exit(0)
print("бэкап: %s" % бэкап)
print("=== ENGER СВОЙ БРЕНД: ПРИМЕНЕНО ===")
