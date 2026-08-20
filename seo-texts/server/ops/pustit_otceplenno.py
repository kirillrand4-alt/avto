# -*- coding: utf-8 -*-
"""Пустить длинный оп ОТЦЕПЛЁННО: он переживёт задание панели.

Панельная очередь режет ЛЮБОЕ задание на 1800 секундах и убивает процесс.
Партия 20.08 на 200 писем Meyer умерла ровно так: тридцать две минуты
ушли в заслон покупателя, а на генерацию времени не осталось - ни одного
письма, при живом лимите прогона в 3450 секунд. Свой «--timeout=3900»
серверный потолок не поднимает, это потолок ТОЙ стороны.

Здесь стартуем через Start-Process: powershell выходит сразу, процесс
остаётся жить сам по себе и ребёнком задания не числится. Вывод пишем в
файл рядом с журналом - stdout задания нам всё равно не достанется.

Запуск: pustit_otceplenno.py <имя_скрипта_в__ops.py> [аргументы...]
"""
import os
import subprocess
import sys
import time

ПИТОН = r"C:\Program Files\Python311\python.exe"
КАТАЛОГ = r"C:\sender\_ops"

if len(sys.argv) < 2:
    print("нужно имя скрипта")
    raise SystemExit(2)

имя = os.path.basename(sys.argv[1])
скрипт = os.path.join(КАТАЛОГ, имя)
if not os.path.exists(скрипт):
    print(f"нет файла {скрипт} - сначала polozhit_v_ops.py")
    raise SystemExit(2)

метка = time.strftime("%m%d-%H%M%S")
основа = os.path.join(КАТАЛОГ, f"{os.path.splitext(имя)[0]}-{метка}")
лог, ошибки = основа + ".log", основа + ".err"

арг = [скрипт] + sys.argv[2:]
список = ", ".join("'" + a.replace("'", "''") + "'" for a in арг)
ком = (f"$env:PYTHONIOENCODING='utf-8'; "
       f"Start-Process -FilePath '{ПИТОН}' -ArgumentList {список} "
       f"-WindowStyle Hidden -RedirectStandardOutput '{лог}' "
       f"-RedirectStandardError '{ошибки}'")
subprocess.run(["powershell", "-NoProfile", "-Command", ком], timeout=90)
print("пущено отцеплённо:", " ".join(арг[1:]))
print("лог:", лог)
print("ошибки:", ошибки)
