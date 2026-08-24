# -*- coding: utf-8 -*-
"""Живы ли прогоны и отвечает ли шлюз на opus-4-6 против opus-4-8.

Владелец 24.08: «у нас писала раньше 4.8 опус». Прогоны с явным
model=claude-opus-4-6 стоят без единого письма. Проверяем догадку замером,
а не рассуждением: короткий вызов каждой модели с потолком в несколько
токенов.
"""
import io
import os
import subprocess
import sys
import time

sys.path.insert(0, r"C:\sender\sender")
sys.path.insert(0, r"C:\sender")
import gen_provider                                            # noqa: E402


def _ps(s, t=60):
    cmd = ('powershell -NoProfile -ExecutionPolicy Bypass -Command "%s"'
           % s.replace('"', '\\"'))
    try:
        p = subprocess.run(cmd, shell=True, capture_output=True, timeout=t)
        return ((p.stdout or b"") + (p.stderr or b"")).decode("cp866", "replace").strip()
    except Exception as e:
        return "ОШИБКА: %s" % e


print("=== ПРОЦЕССЫ ГЕНЕРАЦИИ ===")
print(_ps("Get-CimInstance Win32_Process -Filter \\\"Name like 'python%'\\\" | "
          "Where-Object {$_.CommandLine -match 'partiya_gen'} | "
          "ForEach-Object { $_.ProcessId.ToString() + ' | ' + $_.CommandLine }"))

print("\n=== ХВОСТЫ ЛОГОВ ===")
кат = r"C:\sender\_ops"
for имя in sorted(os.listdir(кат)):
    if имя.startswith("partiya_gen-0824") and имя.endswith(".log"):
        п = os.path.join(кат, имя)
        возраст = int(time.time() - os.path.getmtime(п))
        текст = io.open(п, encoding="utf-8", errors="replace").read()
        print("-- %s (%d байт, изменён %d с назад)" % (имя, len(текст), возраст))
        print(текст[-1200:])

print("\n=== ОТВЕЧАЮТ ЛИ МОДЕЛИ ===")
клиент = gen_provider.make_client()
for модель in ("claude-opus-4-8", "claude-opus-4-6", "claude-sonnet-4-6"):
    т0 = time.time()
    try:
        от = gen_provider.call(клиент, "Ответь одним словом: готов", модель, 16,
                               thinking=False)
        текст = от[0] if isinstance(от, tuple) else от
        print("%-22s OK  %4.1f c  ответ: %r" % (модель, time.time() - т0,
                                                str(текст)[:60]))
    except Exception as e:                                     # noqa: BLE001
        print("%-22s СБОЙ %4.1f c  %s: %s" % (модель, time.time() - т0,
                                              type(e).__name__, str(e)[:220]))
