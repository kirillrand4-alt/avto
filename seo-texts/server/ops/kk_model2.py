# -*- coding: utf-8 -*-
"""Основная модель kc_kontakty (её берёт допоиск Meyer-7)."""
import io
import re
к = io.open(r"C:\sender\server\kc_kontakty.py", encoding="utf-8", errors="replace").read()
for с in к.splitlines():
    if re.search(r"^\s*МОДЕЛЬ\s*=|^\s*модель\s*=|KC_MODEL'|KC_MODEL\"", с):
        print("   " + с.strip()[:160])
print("=== KK2 ===")
