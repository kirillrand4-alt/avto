# -*- coding: utf-8 -*-
"""Откат правки «сделка без обхода» (владелец 14.10: «не надо»): вернуть
confirm.py и sender.py из бэкапов, сделанных прямо перед ней. py_compile."""
import py_compile
import shutil

for ф, бак in ((r"C:\sender\sender\confirm.py", r"C:\sender\sender\confirm.py.bak-1791960051"),
               (r"C:\sender\sender\sender.py", r"C:\sender\sender\sender.py.bak-1791960071")):
    текст = open(ф, encoding="utf-8").read()
    if "БЕЗ ОБХОДА" not in текст:
        print("уже без правки:", ф)
        continue
    shutil.copy2(бак, ф)
    py_compile.compile(ф, doraise=True)
    print("откачено:", ф, "| маркер остался:", "БЕЗ ОБХОДА" in open(ф, encoding="utf-8").read(),
          "| заслон сделок на месте:", "deal_in_division" in open(ф, encoding="utf-8").read())
print("=== ОТКАТ БЕЗ ОБХОДА ===")
