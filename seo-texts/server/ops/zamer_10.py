# -*- coding: utf-8 -*-
"""Цена писем последнего запуска «Россия 9000» (без двойного счёта строк)."""
import io
import json
import os
import subprocess

ЖУРНАЛ = r"C:\sender\_ops\gen-rossiya-9000.jsonl"
лог = io.open(r"C:\sender\_ops\gen-rossiya-9000.log", encoding="utf-8",
              errors="replace").read()
посл = лог.rsplit("==== ЗАПУСК", 1)[-1]
print("запуск:" + посл.splitlines()[0][:110])
pid = io.open(r"C:\sender\_ops\gen-rossiya-9000.pid").read().strip()
в = subprocess.run(["tasklist", "/FI", "PID eq %s" % pid], capture_output=True,
                   text=True).stdout
print("процесс %s жив: %s" % (pid, pid in в))
строки = [с for с in посл.splitlines() if "] ОК " in с or "] брак" in с]
for с in строки[-12:]:
    print("   " + с.strip()[:150])
ок = sum(1 for с in строки if "] ОК " in с)
цены = []
for с in строки:
    try:
        цены.append(float(с.split("$")[1].split()[0]))
    except Exception:  # noqa: BLE001
        pass
if строки:
    print("ИТОГ: попыток %d, годных %d, брак %d" % (len(строки), ок, len(строки) - ок))
    print("потрачено $%.2f, за попытку $%.3f, ЗА ГОДНОЕ $%.3f"
          % (sum(цены), sum(цены) / len(цены), sum(цены) / max(1, ок)))
for с in посл.splitlines():
    if "СТОП ПО ЦЕНЕ" in с or "срыв" in с.lower():
        print("   ! " + с.strip()[:160])
print("=== ЗАМЕР ===")
