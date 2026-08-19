# -*- coding: utf-8 -*-
"""Контекст правила про HACCP и правила про обращение по имени."""
import re
import sys

sys.path.insert(0, r"C:\sender")
from sender import ai_letter as AI                               # noqa: E402

т = AI.RULES_BY_DIVISION["meyer"].split("\n")
for i, s in enumerate(т):
    if re.search(r'(?i)haccp|хассп', s):
        print("--- контекст HACCP ---")
        for j in range(max(0, i - 8), min(len(т), i + 6)):
            print(f"  {'>>' if j == i else '  '} {т[j][:104]}")
        break

print("\n--- всё про контакт/имя в правилах Meyer ---")
for i, s in enumerate(т):
    if re.search(r'(?i)контакт|по имени|приветств|здравствуйте', s):
        print(f"  {s[:110]}")

print("\n--- как имя попадает в промпт (_recipient_block) ---")
import inspect                                                   # noqa: E402
исх = inspect.getsource(AI._recipient_block)
for s in исх.split("\n"):
    if re.search(r'(?i)contact|имя|name', s):
        print(f"  {s.strip()[:104]}")
