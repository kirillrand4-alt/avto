# -*- coding: utf-8 -*-
"""Есть ли на этой машине папка дропа - чтобы положить файл напрямую."""
import os

кандидаты = [r"C:\drop", r"C:\sender\drop", r"C:\inetpub\drop",
             r"C:\www\drop", r"C:\parsercompressor\drop",
             r"C:\sender\_drop"]
for п in кандидаты:
    print(f"{п}: {'ЕСТЬ' if os.path.isdir(п) else 'нет'}")
корни = [r"C:\\"]
print("\nпапки в корне C:\\:")
try:
    print(", ".join(sorted(d for d in os.listdir("C:\\")
                           if os.path.isdir(os.path.join("C:\\", d)))[:30]))
except Exception as ex:                                       # noqa: BLE001
    print(f"  не прочлось: {ex}")
