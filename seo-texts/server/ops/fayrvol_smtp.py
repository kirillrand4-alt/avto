# -*- coding: utf-8 -*-
"""Нет ли на самом сервере правила, закрывающего SMTP Яндекса."""
import re
import subprocess

в = subprocess.run(["netsh", "advfirewall", "firewall", "show", "rule",
                    "name=all", "dir=out", "verbose"],
                   capture_output=True, text=True, encoding="cp866",
                   errors="replace").stdout
блоки = в.split("\n\n")
print("исходящих правил: %d" % len(блоки))
нашли = 0
for б in блоки:
    if re.search(r"77\.88\.|465|587|smtp|yandex|Block|Блок", б, re.I) and \
            re.search(r"(Action|Действие):\s*(Block|Блокировать)", б, re.I):
        нашли += 1
        print("--- правило ---")
        for с in б.splitlines():
            if re.match(r"\s*(Rule Name|Имя правила|Enabled|Включено|Action|"
                        r"Действие|RemoteIP|Удаленный IP|RemotePort|"
                        r"Удаленный порт|Program|Программа)", с):
                print("   " + с.strip()[:120])
print("блокирующих исходящих правил по SMTP/Яндексу: %d" % нашли)
м = subprocess.run(["netsh", "advfirewall", "show", "allprofiles", "state"],
                   capture_output=True, text=True, encoding="cp866",
                   errors="replace").stdout
print(" ".join(м.split())[:300])
т = subprocess.run(["tracert", "-d", "-h", "12", "-w", "1500", "77.88.21.158"],
                   capture_output=True, text=True, encoding="cp866",
                   errors="replace").stdout
print("--- маршрут до smtp.yandex.ru ---")
print("\n".join(т.splitlines()[-14:]))
print("=== ФАЙРВОЛ ===")
