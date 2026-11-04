# -*- coding: utf-8 -*-
"""Показать строки серверного auto_send.py: pokaz_auto_send.py ОТ ДО (только чтение)."""
import io, sys
т = io.open(r"C:\sender\sender\auto_send.py", encoding="utf-8").read().splitlines()
for j in range(int(sys.argv[1]) - 1, min(len(т), int(sys.argv[2]))):
    print("%5d|%s" % (j + 1, т[j]))
