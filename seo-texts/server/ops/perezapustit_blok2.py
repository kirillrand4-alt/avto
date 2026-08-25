# -*- coding: utf-8 -*-
"""Остановить блок КЦ и перезапустить без предклассификатора.

БЕДА. На старте блока gpt-5.4-mini перестал отвечать («стрим молчит 90с,
шлюз шлёт только ping»), и предклассификатор ушёл на запасную модель. За
час она отсеяла 2386 компаний как «не наше направление», и 57% из них —
обрабатывающие производства и стройка: «Азот-2» (промышленные газы),
«Авангард» (чугун и сталь), «Агро-Мехобработка», «Водосети Кузбасса»,
дорожники. Это профиль КЦ по определению — так написано в самом промпте
предкласса («металлообработка, металлоконструкции, дороги»).

ЧТО ДЕЛАЕМ. Останавливаем блок (писем он ещё не написал ни одного, терять
нечего), отменяем сожжённые попытки и пускаем заново с --bez-predklassa.
Качество при этом не падает без присмотра: платный гейт адресата остаётся
на месте, он в блоке Meyer срезал 1262 кандидата до 404.

ПОЧЕМУ ОТМЕНЯЕМ ПОПЫТКИ. Каждый отсев записан в журнал как попытка, а на
третьей компания выбывает из партии навсегда. Пусть выбывают за дело, а не
за час, когда шлюз молчал. Отмена — отдельная строка в журнале, ничего не
удаляем (тот же приём, что у ops/otkatit_403_popytki.py).

    pl_run.py perezapustit_blok2.py            # вхолостую
    pl_run.py perezapustit_blok2.py primenit   # остановить и перезапустить
"""
import io
import json
import os
import subprocess
import sys
import time

КАТАЛОГ = r"C:\sender\_ops"
ЖУРНАЛ = os.path.join(КАТАЛОГ, "gen-partiya-935.jsonl")
ДЕЛАТЬ = "primenit" in sys.argv[1:]

# ---- кого остановить -------------------------------------------------------
в = subprocess.run(
    ["powershell", "-NoProfile", "-Command",
     "Get-CimInstance Win32_Process -Filter \"name like '%python%'\" | "
     "Where-Object {$_.CommandLine -like '*partiya_gen*' -or "
     "$_.CommandLine -like '*ochered_25_08*'} | "
     "Select-Object ProcessId,@{n='cmd';e={$_.CommandLine}} | ConvertTo-Json -Compress"],
    capture_output=True, timeout=60)
т = (в.stdout or b"").decode("utf-8", "replace").strip()
процессы = []
if т:
    д = json.loads(т)
    процессы = д if isinstance(д, list) else [д]
for п in процессы:
    print("   pid %-7s %s" % (п["ProcessId"], str(п["cmd"])[:110]))

# ---- сколько попыток сожжено ----------------------------------------------
with io.open(ЖУРНАЛ, "rb") as ф:
    ф.seek(max(0, os.path.getsize(ЖУРНАЛ) - 1200000))
    хвост = ф.read().decode("utf-8", "replace").splitlines()[1:]
жертвы = []
for с in хвост:
    try:
        з = json.loads(с)
    except Exception:  # noqa: BLE001
        continue
    if з.get("этап") == "предкласс_отсев" and з.get("направление") == "kc":
        жертвы.append((str(з.get("inn") or ""), з.get("имя") or ""))
print("\nотсеяно предклассом в этом блоке: %d — им вернём попытку" % len(жертвы))

if not ДЕЛАТЬ:
    print("\nвхолостую. Остановить и перезапустить — primenit")
    raise SystemExit(0)

for п in процессы:
    subprocess.run(["taskkill", "/PID", str(п["ProcessId"]), "/F"],
                   capture_output=True, timeout=30)
    print("остановлен pid %s" % п["ProcessId"])
time.sleep(3)

with io.open(ЖУРНАЛ, "a", encoding="utf-8") as ф:
    for инн, имя in жертвы:
        ф.write(json.dumps(
            {"этап": "отмена_попытки", "inn": инн, "имя": имя,
             "почему": "предкласс на запасной модели резал свой же профиль "
                       "(25.08, 57% отсева - производство и стройка)",
             "ts": time.time()}, ensure_ascii=False) + "\n")
    ф.flush()
    os.fsync(ф.fileno())
print("отмен попыток записано: %d" % len(жертвы))

лог = os.path.join(КАТАЛОГ, "ochered2508-blok2b-kc.log")
аргументы = ['"C:\\Program Files\\Python311\\python.exe"',
             os.path.join(КАТАЛОГ, "partiya_gen.py"),
             "2300", "50000", "kc", "0", "porog=2.50",
             "model=claude-sonnet-4-6", "--bez-predklassa"]
команда = ("Start-Process -FilePath '%s' -ArgumentList '%s' "
           "-WorkingDirectory '%s' -WindowStyle Hidden "
           "-RedirectStandardOutput '%s' -RedirectStandardError '%s'"
           % (r"C:\Program Files\Python311\python.exe",
              "','".join(аргументы[1:]), КАТАЛОГ, лог, лог + ".err"))
з = subprocess.run(["powershell", "-NoProfile", "-Command", команда],
                   capture_output=True, timeout=60)
print("перезапуск: rc=%s %s"
      % (з.returncode, (з.stdout or з.stderr).decode("cp866", "replace")[:200]))
