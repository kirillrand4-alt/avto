# -*- coding: utf-8 -*-
"""Ход замерочного прогона partiya_gen по «Россия 9000»: письма и цена."""
import io
import json
import os
import subprocess

ЖУРНАЛ = r"C:\sender\_ops\gen-rossiya-9000.jsonl"
pid = io.open(r"C:\sender\_ops\gen-rossiya-9000.pid").read().strip()
в = subprocess.run(["tasklist", "/FI", "PID eq %s" % pid], capture_output=True,
                   text=True).stdout
print("процесс %s жив: %s" % (pid, pid in в))
строки = []
if os.path.exists(ЖУРНАЛ):
    for с in io.open(ЖУРНАЛ, encoding="utf-8"):
        try:
            строки.append(json.loads(с))
        except Exception:  # noqa: BLE001
            pass
ген = [z for z in строки if z.get("цена_$") is not None]
годных = [z for z in ген if z.get("тело")]
print("записей журнала: %d, попыток с ценой: %d, годных: %d"
      % (len(строки), len(ген), len(годных)))
сумма = sum(float(z.get("цена_$") or 0) for z in ген)
пис = sum(float(z.get("цена_письма_$") or 0) for z in ген)
пров = sum(float(z.get("цена_проверок_$") or 0) for z in ген)
if ген:
    print("потрачено всего: $%.2f (письмо $%.2f + проверки $%.2f)" % (сумма, пис, пров))
    print("за попытку: $%.3f" % (сумма / len(ген)))
if годных:
    print("ЗА ГОДНОЕ ПИСЬМО: $%.3f" % (сумма / len(годных)))
for z in ген[-6:]:
    print("   %-28s %-6s $%.3f  вызовов %s"
          % (str(z.get("имя") or z.get("email") or "")[:28],
             "ок" if z.get("тело") else "брак", float(z.get("цена_$") or 0),
             z.get("вызовов")))
т = io.open(r"C:\sender\_ops\gen-rossiya-9000.log", encoding="utf-8",
            errors="replace").read()
print("--- хвост лога ---")
print(т[-900:])
print("=== ХОД 9000 ===")
