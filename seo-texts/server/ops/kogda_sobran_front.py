# -*- coding: utf-8 -*-
"""Когда собран серверный бандл фронта - и не новее ли он моего исходника.

Мой билд весит 351 КБ, серверный - 377 КБ. Разница означает, что серверный
собран с ДРУГОГО исходника: скорее всего соседняя сессия что-то добавила в
экраны. Класть свой бандл поверх - откатить её работу. Смотрим даты.
"""
import datetime
import os

for корень in (r"C:\sender\sender\web\dist", r"C:\sender\web\dist"):
    if not os.path.isdir(корень):
        continue
    print(f"\n{корень}")
    for путь, _, файлы in os.walk(корень):
        for ф in файлы:
            п = os.path.join(путь, ф)
            т = datetime.datetime.utcfromtimestamp(os.path.getmtime(п))
            print(f"   {os.path.relpath(п, корень):<38} {os.path.getsize(п):>9}  "
                  f"изменён {т:%Y-%m-%d %H:%M} UTC")
