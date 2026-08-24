# -*- coding: utf-8 -*-
"""Снять дешёвый прогон и показать, что он успел."""
import io
import json
import os
import subprocess

вывод = subprocess.run(
    ["wmic", "process", "where", "name='python.exe'", "get",
     "ProcessId,CommandLine", "/format:list"],
    capture_output=True, text=True, timeout=60).stdout
пары, ком = [], ""
for с in вывод.splitlines():
    с = с.strip()
    if с.startswith("CommandLine="):
        ком = с
    elif с.startswith("ProcessId=") and с.split("=", 1)[1].strip():
        пары.append((с.split("=", 1)[1].strip(), ком))
цели = [п for п, к in пары if "partiya_deshevaya" in к]
if not цели:
    print("процессов дешёвого прогона нет")
for пид in цели:
    r = subprocess.run(["taskkill", "/PID", пид, "/F"],
                       capture_output=True, text=True, timeout=60)
    print("убит pid=%s: %s" % (пид, (r.stdout or r.stderr).strip()[:80]))

п = r"C:\sender\_ops\deshevaya-partiya.jsonl"
if os.path.exists(п):
    строки = [json.loads(с) for с in io.open(п, encoding="utf-8") if с.strip()]
    годных = [з for з in строки if з.get("ок")]
    вочередь = [з for з in годных if з.get("review_id")]
    print("\nотчёт: строк %d | годных %d | ИЗ НИХ ПОЛОЖЕНО В ОЧЕРЕДЬ %d"
          % (len(строки), len(годных), len(вочередь)))
    print("потрачено: $%.3f"
          % sum(float(з.get("цена_$") or 0) for з in строки))
    if вочередь:
        print("\nчто уже в очереди (последние 8):")
        for з in вочередь[-8:]:
            print("  #%-6s %-34s %s" % (з.get("review_id"),
                                        str(з.get("имя"))[:34],
                                        str(з.get("направление"))))
else:
    print("\nотчёта нет — прогон не успел ничего записать")
