# -*- coding: utf-8 -*-
"""Поставить сверку спам-папок в расписание: раз в сутки.

Сторож читает только INBOX, и ответ, улетевший в «Спам», не увидит никто.
Раз в сутки проходим спам-папки и забираем письма от НАШИХ получателей.

    pl_run.py postavit_sverku_spama.py primenit
"""
import io
import os
import subprocess
import sys

ИМЯ = "sender-sverka-spama"
ОБЁРТКА = r"C:\sender\_ops\sverka-spama.cmd"
ПИТОН = r"C:\Program Files\Python311\python.exe"
СКРИПТ = r"C:\sender\server\ops\sverka_spama.py"
ЛОГ = r"C:\sender\_ops\sverka-spama.log"
ДЕЛАТЬ = "primenit" in sys.argv[1:]

ТЕЛО = ("@echo off\r\n"
        "rem Sverka spam-papok: otvety ot nashih poluchateley v lentu lidov.\r\n"
        'echo ==== %DATE% %TIME% >> "' + ЛОГ + '"\r\n'
        '"' + ПИТОН + '" "' + СКРИПТ + '" primenit >> "' + ЛОГ + '" 2>&1\r\n')
есть = subprocess.run(["schtasks", "/query", "/tn", ИМЯ],
                      capture_output=True, timeout=40)
print("задача сейчас: %s" % ("есть" if есть.returncode == 0 else "нет"))
if not ДЕЛАТЬ:
    print("вхолостую. Завести — primenit")
    raise SystemExit(0)
io.open(ОБЁРТКА, "w", encoding="ascii", newline="").write(ТЕЛО)
в = subprocess.run(["schtasks", "/create", "/tn", ИМЯ, "/tr", ОБЁРТКА,
                    "/sc", "daily", "/st", "05:40", "/ru", "SYSTEM", "/f"],
                   capture_output=True, text=True, timeout=60)
print("создание: rc=%s %s" % (в.returncode,
                              (в.stdout or в.stderr or "").strip()[:160]))
