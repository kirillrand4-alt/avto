# -*- coding: utf-8 -*-
"""Оставить ровно ОДИН прогон генерации, лишние убить.

Серверный процесс переживает смерть локального драйвера. Цепочка
перезапускалась несколько раз, и на сервере накопилось три прогона по
одному и тому же списку: полтораста параллельных вызовов провайдера, письма
одним и тем же фирмам, две трети работы выбрасывается дедупом по ИНН.
Отсюда и «денег ушло, а писем нет».

Убиваем ВСЕ: чистое состояние надёжнее попытки угадать, какой из трёх
здоровее. Следующий круг цепочки поднимет ровно один.
"""
import subprocess

out = subprocess.run(["wmic", "process", "where", "name='python.exe'",
                      "get", "ProcessId,CommandLine"],
                     capture_output=True, text=True, timeout=40).stdout
пиды = []
for l in out.splitlines():
    if "_gen_partiya" not in l:
        continue
    ч = l.split()
    if ч and ч[-1].isdigit():
        пиды.append(int(ч[-1]))
print("нашёл прогонов:", пиды)
for pid in пиды:
    r = subprocess.run(["taskkill", "/PID", str(pid), "/F"],
                       capture_output=True, text=True, timeout=30)
    print(f"  убит {pid}: rc={r.returncode} {r.stdout.strip()[:60]}")
print("убито:", len(пиды))
