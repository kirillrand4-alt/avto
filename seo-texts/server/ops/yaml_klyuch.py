# -*- coding: utf-8 -*-
"""Строки sender.yaml с подстрокой и проверка загрузки конфига: yaml_klyuch.py <подстрока>"""
import io
import sys
sys.path.insert(0, r"C:\sender")
for i, с in enumerate(io.open(r"C:\sender\sender.yaml", encoding="utf-8"), 1):
    if sys.argv[1] in с:
        print(i, с.rstrip())
from sender.config import Config  # noqa: E402
к = Config.load(r"C:\sender\sender.yaml")
print("конфиг грузится; gates.otkaz_stop_napravlenie =", к.get("gates.otkaz_stop_napravlenie", None))
print("=== YAML ===")
