# -*- coding: utf-8 -*-
"""Только чтение: точный вызов подбора ящика в боевом цикле."""
import io

лн = io.open(r"C:\sender\sender\auto_send.py", encoding="utf-8",
             errors="replace").read().splitlines()
for i in range(334, 372):
    print("%4d|%s" % (i + 1, лн[i]))
