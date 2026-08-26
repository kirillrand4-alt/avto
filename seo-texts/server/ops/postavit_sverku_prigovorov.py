# -*- coding: utf-8 -*-
"""Поставить сверку приговоров в расписание Windows.

Раз в час: вердикт «мёртв» обязан за час дойти до стоп-листа, обогащения и
очереди. Зовём .cmd-обёртку — у schtasks беда с кавычками в «Program Files»,
а обёртка заодно копит вывод в лог.

    pl_run.py postavit_sverku_prigovorov.py            # вхолостую
    pl_run.py postavit_sverku_prigovorov.py primenit   # завести
"""
import io
import os
import subprocess
import sys

ИМЯ = "sender-sverka-prigovorov"
ОБЁРТКА = r"C:\sender\_ops\sverka-prigovorov.cmd"
ПИТОН = r"C:\Program Files\Python311\python.exe"
СКРИПТ = r"C:\sender\server\ops\sverka_prigovorov.py"
ЛОГ = r"C:\sender\_ops\sverka-prigovorov.log"
ДЕЛАТЬ = "primenit" in sys.argv[1:]

ТЕЛО = (
    "@echo off\r\n"
    "rem Sverka prigovorov: mertvyy adres dolzhen vypast iz raboty celikom.\r\n"
    'echo ==== %DATE% %TIME% >> "' + ЛОГ + '"\r\n'
    '"' + ПИТОН + '" "' + СКРИПТ + '" primenit >> "' + ЛОГ + '" 2>&1\r\n'
)
print("обёртка: %s" % ОБЁРТКА)
есть = subprocess.run(["schtasks", "/query", "/tn", ИМЯ],
                      capture_output=True, timeout=40)
print("задача сейчас: %s" % ("есть" if есть.returncode == 0 else "нет"))
if not ДЕЛАТЬ:
    print("\nвхолостую. Завести — primenit")
    raise SystemExit(0)

os.makedirs(os.path.dirname(ОБЁРТКА), exist_ok=True)
io.open(ОБЁРТКА, "w", encoding="ascii", newline="").write(ТЕЛО)
print("обёртка записана")
в = subprocess.run(["schtasks", "/create", "/tn", ИМЯ, "/tr", ОБЁРТКА,
                    "/sc", "hourly", "/mo", "1", "/ru", "SYSTEM", "/f"],
                   capture_output=True, text=True, timeout=60)
print("создание: rc=%s %s" % (в.returncode,
                              (в.stdout or в.stderr or "").strip()[:200]))
пр = subprocess.run(["schtasks", "/query", "/tn", ИМЯ, "/fo", "LIST"],
                    capture_output=True, text=True, timeout=40)
print((пр.stdout or "").strip()[:600])
