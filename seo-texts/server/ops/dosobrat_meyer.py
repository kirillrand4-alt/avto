# -*- coding: utf-8 -*-
"""Добрать 62 недобранных мейеровских кода. Запуск через планировщик.

Почему перезапуск теперь безопасен: в data/agro-base.progress.json лежит
done_codes на 13 кодов — сборщик их пропустит сам, повторного прожига не будет.

Ключи: в api_keys.txt 419 записей, из них 405 отвечают «API-ключ не
действителен». Сборщик крутил бы их вхолостую, поэтому кладём в файл только 14
живых, а полный список сохраняем рядом (откатить — переименовать обратно).
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
КЛЮЧИ = os.path.join(КОРЕНЬ, "data", "api_keys.txt")
ЖИВЫЕ = r"C:\sender\_ops\checko-zhivye-klyuchi.txt"

живые = [с.strip() for с in io.open(ЖИВЫЕ, encoding="utf-8") if с.strip()]
print("живых ключей к запуску: %d" % len(живые))
if len(живые) < 5:
    print("ключей слишком мало — не запускаю")
    raise SystemExit(0)

тело = (
    "@echo off\r\n"
    "cd /d %s\r\n" % КОРЕНЬ +
    ".venv\\Scripts\\python.exe scripts\\daily_collect.py "
    "--okved-file data\\okved-agro.txt --csv data\\agro-base.csv "
    "--no-contacts --main-okved-only --no-xlsx --no-key-check "
    "--delay 0.4 --concurrency 4 "
    ">> %s 2>&1\r\n" % ЛОГ)
print("команда:\n%s" % тело)

if not КАТИТЬ:
    print("[сухой прогон] с --katit подменю ключи и заведу задание")
    raise SystemExit(0)

запас = os.path.join(КОРЕНЬ, "data", "api_keys-vse-%d.txt" % int(time.time()))
if not os.path.exists(запас):
    with io.open(КЛЮЧИ, encoding="utf-8", errors="replace") as f:
        было = f.read()
    with io.open(запас, "w", encoding="utf-8") as f:
        f.write(было)
        f.flush()
        os.fsync(f.fileno())
    print("полный список сохранён: %s (%d Б)" % (запас, len(было)))
with io.open(КЛЮЧИ, "w", encoding="utf-8") as f:
    f.write("\n".join(живые) + "\n")
    f.flush()
    os.fsync(f.fileno())
print("в api_keys.txt теперь %d живых ключей" % len(живые))

with io.open(BAT, "w", encoding="utf-8", newline="") as f:
    f.write(тело)
    f.flush()
    os.fsync(f.fileno())
subprocess.run(["schtasks", "/End", "/TN", ИМЯ], capture_output=True,
               text=True, timeout=60)
subprocess.run(["schtasks", "/Delete", "/TN", ИМЯ, "/F"], capture_output=True,
               text=True, timeout=60)
когда = time.strftime("%H:%M", time.localtime(time.time() + 180))
r = subprocess.run(["schtasks", "/Create", "/TN", ИМЯ, "/SC", "ONCE",
                    "/ST", когда, "/RU", "SYSTEM", "/RL", "HIGHEST", "/F",
                    "/TR", BAT], capture_output=True, text=True, timeout=60)
print("создание задания: %s%s" % ((r.stdout or "").strip()[:80],
                                  (r.stderr or "").strip()[:80]))
r = subprocess.run(["schtasks", "/Run", "/TN", ИМЯ], capture_output=True,
                   text=True, timeout=60)
print("запуск: %s%s" % ((r.stdout or "").strip()[:80],
                        (r.stderr or "").strip()[:80]))

было_лог = os.path.getsize(ЛОГ) if os.path.exists(ЛОГ) else 0
time.sleep(50)
стало = os.path.getsize(ЛОГ) if os.path.exists(ЛОГ) else 0
хвост = []
if os.path.exists(ЛОГ):
    хвост = io.open(ЛОГ, encoding="utf-8", errors="replace").read().splitlines()[-8:]
print("\n=== ХВОСТ ЛОГА ЧЕРЕЗ 50 С ===")
for с in хвост:
    print("   %s" % с[:150])
print("\n=== ИТОГ ===")
print("лог вырос на %d Б — %s" % (стало - было_лог,
      "прогон пошёл" if стало > было_лог else "движения пока нет"))
print("ожидаем: 62 кода, ≈64 390 компаний, ≈675 запросов при потолке ≈1400")
