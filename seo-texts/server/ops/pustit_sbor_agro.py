# -*- coding: utf-8 -*-
"""Запустить сбор компаний по 99 кодам через готовый daily_collect.py.

Прогон длинный (счёт на десятки тысяч компаний), поэтому вешаем его на разовое
задание планировщика: оно живёт своим процессом и переживает и потолок задания
в 1800 секунд, и перезапуск панели. Тот же приём, что для рестарта службы —
прямой Popen умирает вместе с деревом службы.

Ключи: --no-key-check, чтобы не жечь запросы на предварительную проверку 881
ключа. Контакты не трогаем: --no-contacts, это отдельный прогон
enrich_contacts.py. Excel не собираем на каждом заходе.
"""
import io
import os
import subprocess
import sys
import time

КАТИТЬ = "--katit" in sys.argv
ИМЯ = "AgroOkvedCollectOnce"
КОРЕНЬ = r"C:\seostat\Parser2"
BAT = r"C:\sender\_ops\sbor-agro.cmd"
ЛОГ = r"C:\sender\_ops\sbor-agro.log"
КОДЫ = os.path.join(КОРЕНЬ, "data", "okved-agro.txt")
CSV = os.path.join(КОРЕНЬ, "data", "agro-base.csv")

n = sum(1 for с in io.open(КОДЫ, encoding="utf-8") if с.strip())
print("кодов в списке: %d" % n)
print("csv: %s (%s)" % (CSV, "есть" if os.path.exists(CSV) else "будет создан"))

тело = (
    "@echo off\r\n"
    "cd /d %s\r\n" % КОРЕНЬ +
    ".venv\\Scripts\\python.exe scripts\\daily_collect.py "
    "--okved-file data\\okved-agro.txt --csv data\\agro-base.csv "
    "--no-contacts --main-okved-only --no-xlsx --no-key-check "
    ">> %s 2>&1\r\n" % ЛОГ)
print("\nкоманда:\n%s" % тело)

if not КАТИТЬ:
    print("[сухой прогон] с --katit заведу задание планировщика")
    raise SystemExit(0)

with io.open(BAT, "w", encoding="utf-8", newline="") as f:
    f.write(тело)
    f.flush()
    os.fsync(f.fileno())
subprocess.run(["schtasks", "/Delete", "/TN", ИМЯ, "/F"],
               capture_output=True, text=True, timeout=60)
когда = time.strftime("%H:%M", time.localtime(time.time() + 120))
r = subprocess.run(["schtasks", "/Create", "/TN", ИМЯ, "/SC", "ONCE",
                    "/ST", когда, "/RU", "SYSTEM", "/RL", "HIGHEST", "/F",
                    "/TR", BAT], capture_output=True, text=True, timeout=60)
print("создание задания (%s): %s" % (r.returncode,
                                     (r.stdout or r.stderr).strip()[:160]))
r = subprocess.run(["schtasks", "/Run", "/TN", ИМЯ], capture_output=True,
                   text=True, timeout=60)
print("запуск (%s): %s" % (r.returncode, (r.stdout or r.stderr).strip()[:160]))
print("лог: %s" % ЛОГ)
