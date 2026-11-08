# -*- coding: utf-8 -*-
"""Показать образцы из _ops/obrazcy-imennye-kc.txt по номерам: chitat_obrazcy.py ОТ ДО"""
import io, re, sys
т = io.open(sys.argv[3] if len(sys.argv) > 3 else r"C:\sender\_ops\obrazcy-imennye-kc.txt", encoding="utf-8").read()
куски = re.split(r"(?m)^(?==== )", т)
for к in куски:
    м = re.match(r"=== (\d+)\.", к)
    if м and int(sys.argv[1]) <= int(м.group(1)) <= int(sys.argv[2]):
        print(к.rstrip() + "\n")
