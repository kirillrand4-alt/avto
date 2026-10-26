# -*- coding: utf-8 -*-
"""Положить STOP-файл дирижёру яруса C (_ops/v4c-pachki.STOP)."""
open(r"C:\sender\_ops\v4c-pachki.STOP", "w").write("стоп 26.10: топ-2000 разобран, зацикливание на 6 пропусках")
print("STOP положен")
