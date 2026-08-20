# -*- coding: utf-8 -*-
"""Был ли за вердиктом настоящий SMTP-диалог: код и ответ сервера.

Владелец: «может через основной сервер они проверялись». Проверяем по
следу: у SMTP-пробы в строке остаются code (250, 550…) и answer — текст
чужого сервера. У DNS-проверки их нет.
"""
import sqlite3
from collections import Counter

c = sqlite3.connect(r"C:\sender\sender.db")
c.row_factory = sqlite3.Row

print("== строки с ПУСТЫМ source ==")
пары = Counter()
коды = Counter()
примеры = {}
for r in c.execute("SELECT verdict, code, COALESCE(answer,'') a, "
                   "COALESCE(mx,'') mx FROM addr_probe "
                   "WHERE source IS NULL OR source=''"):
    в = str(r["verdict"])
    есть_код = r["code"] is not None
    есть_ответ = bool(str(r["a"]).strip())
    пары[(в, "код есть" if есть_код else "кода нет",
          "ответ есть" if есть_ответ else "ответа нет")] += 1
    if есть_код:
        коды[(в, int(r["code"]))] += 1
    if в not in примеры and (есть_ответ or есть_код):
        примеры[в] = f"code={r['code']} answer={str(r['a'])[:80]} mx={r['mx'][:28]}"
for (в, k, a), n in пары.most_common(12):
    print(f"  {n:>6}  {в:<16} {k:<9} {a}")
print("\n  коды:", dict(коды.most_common(8)))
print("  примеры:")
for в, п in примеры.items():
    print(f"    {в:<16} {п}")

print("\n== для сравнения: source='проба' (работник) ==")
пары2 = Counter()
примеры2 = {}
for r in c.execute("SELECT verdict, code, COALESCE(answer,'') a FROM addr_probe "
                   "WHERE source='проба'"):
    в = str(r["verdict"])
    пары2[(в, "код есть" if r["code"] is not None else "кода нет")] += 1
    if в not in примеры2:
        примеры2[в] = f"code={r['code']} answer={str(r['a'])[:80]}"
for (в, k), n in пары2.most_common(8):
    print(f"  {n:>6}  {в:<16} {k}")
print("  примеры:")
for в, п in примеры2.items():
    print(f"    {в:<16} {п}")
