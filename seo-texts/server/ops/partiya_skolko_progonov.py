# -*- coding: utf-8 -*-
"""Сколько прогонов генерации живо на сервере. Ничего не трогаем.

ИМЯ СКРИПТА ИЩЕМ В ДВУХ ВИДАХ. Счётчик искал только «_gen_partiya» - имя
файла в песочнице той сессии, где он писался. В репозитории скрипт зовётся
partiya_gen.py и заливается как C:\\sender\\_ops\\partiya_gen.py, то есть
подстрока «_gen_partiya» в его командной строке не встречается ВООБЩЕ.
Счётчик отвечал бы «прогонов: 0» при живом прогоне - ровно та слепота, из-за
которой 17.08 на сервере оказалось три прогона разом. Держим оба имени,
пока в песочницах могут висеть старые запуски.
"""
import subprocess

МЕТКИ = ("_gen_partiya", "partiya_gen")

out = subprocess.run(["wmic", "process", "where", "name='python.exe'",
                      "get", "ProcessId,CommandLine"],
                     capture_output=True, text=True, timeout=40).stdout
пиды = [l.split()[-1] for l in out.splitlines()
        if any(м in l for м in МЕТКИ) and l.split() and l.split()[-1].isdigit()]
print("прогонов:", len(пиды), пиды)
