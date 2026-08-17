# -*- coding: utf-8 -*-
"""Как выглядит фильтр направления в ТОЙ версии api/app.py, что стоит на сервере.

sha256 серверного app.py не совпал с репозиторием (сервер 3f6fa7f…, репо
e73a804…) - значит рассуждать по локальному коду нельзя. Печатаем сам
серверный кусок: разбор параметра, функцию раскладки по направлению и место,
где фильтр уезжает в подбор ящика.

    python zapusk_svoego_skripta.py ops/api_filtr_napravleniya.py
"""
import io
import re
import sys

ФАЙЛ = r"C:\sender\sender\api\app.py"
текст = io.open(ФАЙЛ, encoding="utf-8", errors="replace").read()
строки = текст.splitlines()

ЯКОРЯ = ("_по_направлению", "напр =", "letter_division",
         "ящики его направления", "def _mailbox_candidates",
         "division=", "mailbox")

нужные = set()
for i, s in enumerate(строки):
    if "_по_направлению" in s or "напр = " in s or "letter_division" in s:
        for j in range(max(0, i - 4), min(len(строки), i + 22)):
            нужные.add(j)

прошлая = -2
for i in sorted(нужные):
    if i != прошлая + 1:
        print("   …")
    print(f"{i + 1:5}| {строки[i]}")
    прошлая = i

print("\n--- где фильтр влияет на подбор ящика ---")
for i, s in enumerate(строки):
    if re.search(r"ящик", s) and re.search(r"направлен", s):
        for j in range(max(0, i - 3), min(len(строки), i + 18)):
            print(f"{j + 1:5}| {строки[j]}")
        print("   …")
        break
