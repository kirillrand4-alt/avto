# -*- coding: utf-8 -*-
"""Задачи планировщика Windows, связанные с отправщиком (имя/команда), и их
последний запуск/результат. Только чтение (schtasks /query)."""
import csv
import io
import subprocess
т = subprocess.run(["schtasks", "/query", "/fo", "CSV", "/v"], capture_output=True, text=True, errors="replace").stdout
р = list(csv.reader(io.StringIO(т)))
if not р:
    print("пусто"); raise SystemExit
шапка = р[0]
def поле(r, *имена):
    for и in имена:
        if и in шапка:
            return r[шапка.index(и)]
    return ""
виден = set()
for r in р[1:]:
    if r == шапка or len(r) != len(шапка):
        continue
    имя = поле(r, "TaskName", "Имя задачи")
    кмд = поле(r, "Task To Run", "Задача для выполнения")
    if not any(k in (имя + кмд).lower() for k in ("sender", "inbox", "imap", "pochta", "почт")):
        continue
    if имя in виден:
        continue
    виден.add(имя)
    print(имя, "|", кмд[:120])
    print("   статус:", поле(r, "Status", "Состояние"), "| последний запуск:", поле(r, "Last Run Time", "Время прошлого запуска"),
          "| результат:", поле(r, "Last Result", "Последний результат"), "| след:", поле(r, "Next Run Time", "Время следующего запуска"))
