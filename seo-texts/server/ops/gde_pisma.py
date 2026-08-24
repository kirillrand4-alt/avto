# -*- coding: utf-8 -*-
"""Где письма: логи прогонов, журнал, процессы. БЕЗ вызовов к провайдеру.

Владелец видит по журналу шлюза успешные вызовы opus-4-8 на 9300/565
токенов — это размер письма, за них уплачено. В нашем журнале за сегодня
ноль. Значит письмо либо не доходит до записи, либо пишет его не наш
прогон. Здесь только чтение файлов и списка процессов, чтобы ответ
пришёл за секунды, а не за минуты.
"""
import io
import json
import os
import subprocess
import time

КАТ = r"C:\sender\_ops"
ЖУРНАЛ = os.path.join(КАТ, "gen-partiya-935.jsonl")


def _ps(s, t=45):
    cmd = ('powershell -NoProfile -ExecutionPolicy Bypass -Command "%s"'
           % s.replace('"', '\\"'))
    try:
        p = subprocess.run(cmd, shell=True, capture_output=True, timeout=t)
        return ((p.stdout or b"") + (p.stderr or b"")).decode("cp866", "replace").strip()
    except Exception as e:
        return "ОШИБКА: %s" % e


print("=== ВСЕ PYTHON-ПРОЦЕССЫ ===")
print(_ps("Get-CimInstance Win32_Process -Filter \\\"Name like 'python%'\\\" | "
          "ForEach-Object { '{0}  {1}  {2}' -f $_.ProcessId, "
          "$_.CreationDate.ToString('HH:mm:ss'), "
          "$_.CommandLine.Substring(0,[Math]::Min(150,$_.CommandLine.Length)) }"))

print("\n=== ЛОГИ ПРОГОНОВ 24.08 ===")
for имя in sorted(os.listdir(КАТ)):
    if имя.startswith("partiya_gen-0824") and имя.endswith(".log"):
        п = os.path.join(КАТ, имя)
        возраст = int(time.time() - os.path.getmtime(п))
        текст = io.open(п, encoding="utf-8", errors="replace").read()
        print("\n-- %s | %d байт | не менялся %d с" % (имя, len(текст), возраст))
        print(текст[-2500:])

print("\n=== ЖУРНАЛ ===")
if os.path.exists(ЖУРНАЛ):
    возраст = int(time.time() - os.path.getmtime(ЖУРНАЛ))
    строки = io.open(ЖУРНАЛ, encoding="utf-8", errors="replace").read().splitlines()
    print("строк: %d, файл не менялся %d с" % (len(строки), возраст))
    print("--- последние 6 строк, урезанные ---")
    for с in строки[-6:]:
        try:
            з = json.loads(с)
        except Exception:
            print("  (не json):", с[:200])
            continue
        print("  " + json.dumps(
            {k: (str(v)[:60] if not isinstance(v, (int, float, bool)) else v)
             for k, v in з.items()
             if k in ("этап", "день", "inn", "имя", "ок", "брак", "модель",
                      "сек", "цена_письма_$", "итог", "направление")},
            ensure_ascii=False))
else:
    print("журнала нет")

print("\n=== ПРОЧИЕ СВЕЖИЕ ФАЙЛЫ В _ops (за 3 часа) ===")
сейчас = time.time()
for имя in sorted(os.listdir(КАТ)):
    п = os.path.join(КАТ, имя)
    try:
        в = сейчас - os.path.getmtime(п)
    except OSError:
        continue
    if в < 3 * 3600 and os.path.isfile(п):
        print("  %-46s %6d с назад  %8d б" % (имя[:46], int(в), os.path.getsize(п)))
