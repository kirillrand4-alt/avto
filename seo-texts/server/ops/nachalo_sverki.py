# -*- coding: utf-8 -*-
"""Начало sverka_prigovorov: как строятся приговоры и очередь."""
import io
П = r"C:\sender\server\ops\sverka_prigovorov.py"
т = io.open(П, encoding="utf-8", errors="replace").read().splitlines()
for i, с in enumerate(т[:60], 1):
    print("%4d| %s" % (i, с[:150]))
