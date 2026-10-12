# -*- coding: utf-8 -*-
"""Какие вызовы в ЖИВОМ коде идут без явной модели (= opus по умолчанию).

Владелец 12.10, журнал шлюза: opus-вызовы с огромным входом и крошечным
ответом (63 171 → 55 токенов, $0.65). Короткий ответ — это проверка, а не
письмо. Ищем все default_caller без model= и кто их зовёт.
"""
import io
import os
import re

for имя in sorted(os.listdir(r"C:\sender\sender")):
    if not имя.endswith(".py"):
        continue
    т = io.open(os.path.join(r"C:\sender\sender", имя), encoding="utf-8",
                errors="replace").read().splitlines()
    for н, с in enumerate(т, 1):
        if "default_caller(" in с and "def default_caller" not in с:
            кусок = " ".join(x.strip() for x in т[н - 1:н + 2])
            явно = "model=" in кусок
            print("   %-20s:%-5d %-12s %s" % (имя, н,
                                           "модель явно" if явно else "OPUS(умолч)",
                                           с.strip()[:80]))
        if re.search(r"call = caller or default_caller", с):
            print("   %-20s:%-5d %-12s %s" % (имя, н, "линзы?", с.strip()[:80]))
print("")
print("--- кто передаёт caller в run_lenses / линзы ---")
for имя in sorted(os.listdir(r"C:\sender\sender")):
    if not имя.endswith(".py"):
        continue
    т = io.open(os.path.join(r"C:\sender\sender", имя), encoding="utf-8",
                errors="replace").read().splitlines()
    for н, с in enumerate(т, 1):
        if re.search(r"run_lenses\(|lens_caller|checker=", с) and "def " not in с:
            print("   %-20s:%-5d %s" % (имя, н, с.strip()[:110]))
print("=== КТО ЗОВЁТ OPUS ===")
