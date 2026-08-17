# -*- coding: utf-8 -*-
"""Оставить САМЫЙ СВЕЖИЙ прогон генерации, старшие убить.

Отличие от ops/partiya_ubit_dubli.py: тот убивает ВСЕ прогоны ради чистого
состояния. Это верно, когда непонятно, какой из них здоров, но дорого:
вместе с лишними умирают письма, которые прямо сейчас пишет живой круг, а
они уже оплачены.

Здесь случай другой и известный: серверный процесс переживает смерть
локального драйвера, и осиротевший прогон идёт по ТОМУ ЖЕ списку, что и
живой. Дедуп по ИНН в очереди (dedup_key inn|email|campaign, UNIQUE) вторую
копию письма не пустит - то есть вторая генерация оплачена полностью и
выброшена. Это и есть «деньги ушли, а писем нет» в чистом виде.

Значит убивать надо не все, а СТАРШИЕ по времени старта: живой драйвер
всегда моложе осиротевшего.

    python zapusk_svoego_skripta.py ops/partiya_ubit_lishniy.py
"""
import subprocess

МЕТКИ = ("_gen_partiya", "partiya_gen")

out = subprocess.run(
    ["powershell", "-NoProfile", "-Command",
     "Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | "
     "Select-Object ProcessId,CreationDate,CommandLine | "
     "ForEach-Object { \"$($_.ProcessId)|$($_.CreationDate.ToString('s'))|"
     "$($_.CommandLine)\" }"],
    capture_output=True, text=True, timeout=90).stdout

прогоны = []
for l in out.splitlines():
    if not any(м in l for м in МЕТКИ):
        continue
    ч = l.split("|", 2)
    if len(ч) >= 2 and ч[0].strip().isdigit():
        прогоны.append((ч[1].strip(), int(ч[0].strip()), ч[2][:90] if len(ч) > 2 else ""))

прогоны.sort()
print(f"нашёл прогонов: {len(прогоны)}")
for старт, pid, cmd in прогоны:
    print(f"  pid {pid} старт {старт} | {cmd}")

if len(прогоны) <= 1:
    print("лишних нет, ничего не трогаю")
    raise SystemExit(0)

живой = прогоны[-1]
print(f"\nоставляю самый свежий: pid {живой[1]} (старт {живой[0]})")
for старт, pid, _c in прогоны[:-1]:
    r = subprocess.run(["taskkill", "/PID", str(pid), "/F"],
                       capture_output=True, text=True, timeout=30)
    print(f"  убит {pid} (старт {старт}): rc={r.returncode} "
          f"{r.stdout.strip()[:60]}")
print(f"убито лишних: {len(прогоны) - 1}")
