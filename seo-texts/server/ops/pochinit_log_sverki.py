# -*- coding: utf-8 -*-
"""Лог сверки читаемым: обёртка пишет в UTF-8, а не в кодировке консоли.

Первый прогон лёг в лог кракозябрами: питон печатает UTF-8, а cmd читает
cp866. Ставим кодовую страницу и PYTHONIOENCODING в самой обёртке —
диагностика бесполезна, если её нельзя прочесть.
"""
import io
import os
import subprocess
import time

ОБЁРТКА = r"C:\sender\_ops\sverka-lidov.cmd"
ЛОГ = r"C:\sender\_ops\sverka-lidov.log"
ЖУРНАЛ = r"C:\sender\_ops\sverka-lidov.jsonl"
ПИТОН = r"C:\Program Files\Python311\python.exe"
СКРИПТ = r"C:\sender\server\ops\nochnaya_sverka_lidov.py"

ТЕЛО = (
    "@echo off\r\n"
    "rem Nochnaya sverka lenty lidov: otvet bez kartochki - zavodim kartochku.\r\n"
    "rem Zadacha sender-sverka-lidov, zhurnal ryadom: sverka-lidov.jsonl\r\n"
    "chcp 65001 > nul\r\n"
    "set PYTHONIOENCODING=utf-8\r\n"
    'echo ==== %DATE% %TIME% >> "' + ЛОГ + '"\r\n'
    '"' + ПИТОН + '" "' + СКРИПТ + '" primenit >> "' + ЛОГ + '" 2>&1\r\n'
)
io.open(ОБЁРТКА, "w", encoding="ascii", newline="").write(ТЕЛО)
if os.path.exists(ЛОГ):
    os.remove(ЛОГ)          # старый лог нечитаем, начинаем чистый
print("обёртка обновлена, старый лог убран")

в = subprocess.run(["schtasks", "/run", "/tn", "sender-sverka-lidov"],
                   capture_output=True, timeout=60)
print("прогон: rc=%s" % в.returncode)
time.sleep(14)
print("\n--- лог ---")
if os.path.exists(ЛОГ):
    for с in io.open(ЛОГ, encoding="utf-8", errors="replace").read().splitlines():
        print("   %s" % с)
else:
    print("   лога нет")
print("\n--- durable-журнал ---")
if os.path.exists(ЖУРНАЛ):
    for с in io.open(ЖУРНАЛ, encoding="utf-8").read().splitlines()[-4:]:
        print("   %s" % с)
else:
    print("   журнала нет")
