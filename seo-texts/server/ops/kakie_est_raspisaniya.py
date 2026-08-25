# -*- coding: utf-8 -*-
"""Какие задачи уже стоят в расписании — чтобы новую завести в общем стиле."""
import subprocess

в = subprocess.run(["schtasks", "/query", "/fo", "LIST"],
                   capture_output=True, timeout=60)
т = (в.stdout or b"").decode("cp866", "replace")
интересные = []
блок = {}
for с in т.splitlines():
    с = с.strip()
    if not с:
        if блок:
            интересные.append(блок)
            блок = {}
        continue
    if ":" in с:
        к, з = с.split(":", 1)
        блок[к.strip()] = з.strip()
if блок:
    интересные.append(блок)

нашли = 0
for б in интересные:
    имя = " ".join(з for к, з in б.items() if "мя задачи" in к or "TaskName" in к)
    все = " ".join(б.values()).lower()
    if any(с in все for с in ("sender", "sender.db", "ops\\", "probe", "obzvon",
                              "python")):
        нашли += 1
        print("=== %s" % имя)
        for к, з in б.items():
            if any(п in к for п in ("апуск", "Task To Run", "асписание",
                                    "Schedule", "остояние", "Status",
                                    "Next Run", "ледующ")):
                print("   %-28s %s" % (к, з[:120]))
print("\nвсего задач в системе: %d, похожих на наши: %d"
      % (len(интересные), нашли))
