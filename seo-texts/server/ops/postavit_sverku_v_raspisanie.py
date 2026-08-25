# -*- coding: utf-8 -*-
"""Поставить ночную сверку лидов в расписание Windows.

Задача зовёт не питон напрямую, а .cmd-обёртку: у schtasks своя беда с
кавычками в пути «Program Files», а обёртка заодно копит вывод в лог рядом
с журналом сверки — будет видно и то, что нашли, и то, что упало.

Время 04:10 по машине (она стоит в Москве): окно отправки 09:00–12:00, к
четырём утра вчерашний день закрыт и почта разобрана.

    pl_run.py postavit_sverku_v_raspisanie.py            # вхолостую
    pl_run.py postavit_sverku_v_raspisanie.py primenit   # завести
"""
import io
import os
import subprocess
import sys

ИМЯ = "sender-sverka-lidov"
ОБЁРТКА = r"C:\sender\_ops\sverka-lidov.cmd"
ПИТОН = r"C:\Program Files\Python311\python.exe"
СКРИПТ = r"C:\sender\server\ops\nochnaya_sverka_lidov.py"
ЛОГ = r"C:\sender\_ops\sverka-lidov.log"
ДЕЛАТЬ = "primenit" in sys.argv[1:]

ТЕЛО = (
    "@echo off\r\n"
    "rem Nochnaya sverka lenty lidov: otvet bez kartochki - zavodim kartochku.\r\n"
    "rem Zadacha sender-sverka-lidov, zhurnal ryadom: sverka-lidov.jsonl\r\n"
    'echo ==== %DATE% %TIME% >> "' + ЛОГ + '"\r\n'
    '"' + ПИТОН + '" "' + СКРИПТ + '" primenit >> "' + ЛОГ + '" 2>&1\r\n'
)

print("обёртка: %s" % ОБЁРТКА)
print(ТЕЛО)
есть = subprocess.run(["schtasks", "/query", "/tn", ИМЯ],
                      capture_output=True, timeout=40)
print("задача сейчас: %s"
      % ("есть" if есть.returncode == 0 else "нет"))

if not ДЕЛАТЬ:
    print("\nвхолостую. Завести — primenit")
    raise SystemExit(0)

os.makedirs(os.path.dirname(ОБЁРТКА), exist_ok=True)
io.open(ОБЁРТКА, "w", encoding="ascii", newline="").write(ТЕЛО)
print("обёртка записана")

в = subprocess.run(["schtasks", "/create", "/tn", ИМЯ, "/tr", ОБЁРТКА,
                    "/sc", "daily", "/st", "04:10", "/ru", "SYSTEM", "/f"],
                   capture_output=True, timeout=60)
print("создание: rc=%s %s" % (в.returncode,
                              (в.stdout or в.stderr).decode("cp866", "replace").strip()[:200]))
if в.returncode != 0:
    raise SystemExit("задача не создана")

# Разовый прогон прямо сейчас: пусть докажет, что путь и права рабочие.
п = subprocess.run(["schtasks", "/run", "/tn", ИМЯ], capture_output=True, timeout=60)
print("пробный запуск: rc=%s %s"
      % (п.returncode, (п.stdout or п.stderr).decode("cp866", "replace").strip()[:160]))
import time
time.sleep(12)
if os.path.exists(ЛОГ):
    строки = io.open(ЛОГ, encoding="cp866", errors="replace").read().splitlines()
    print("\n--- хвост лога ---")
    for с in строки[-10:]:
        print("   %s" % с)
else:
    print("лог ещё не появился")
з = subprocess.run(["schtasks", "/query", "/tn", ИМЯ, "/fo", "LIST"],
                   capture_output=True, timeout=40)
for с in (з.stdout or b"").decode("cp866", "replace").splitlines():
    if с.strip():
        print("   %s" % с.strip())
