# -*- coding: utf-8 -*-
"""Отдать файл сервера base64-кусками в stdout — забрать его к себе.

Нужен, когда серверный файл РАЗОШЁЛСЯ с моим: перезаписывать вслепую нельзя
(C:\\sender\\sender\\ общий с соседней сессией), надо сперва посмотреть, что
там на самом деле.
"""
import base64
import sys

путь = sys.argv[1]
b = open(путь, "rb").read()
s = base64.b64encode(b).decode()
print("НАЧАЛО", len(b))
for i in range(0, len(s), 4000):
    print(s[i:i + 4000])
print("КОНЕЦ")
