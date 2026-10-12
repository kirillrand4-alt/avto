# -*- coding: utf-8 -*-
import io
print(io.open(r"C:\sender\_ops\smtp-proba-partiy.log", encoding="utf-8",
              errors="replace").read()[-1800:])
print("=== ЛОГ ПРОБЫ ===")
