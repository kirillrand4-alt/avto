# -*- coding: utf-8 -*-
"""Через сколько мобильные прокси меняют IP. Пишем в durable-файл на сервере.

Каждые 20 секунд спрашиваем внешний адрес по каждому из трёх прокси и
записываем в jsonl с fsync — чтобы замер пережил и рестарт, и обрыв
клиента. Итог печатаем в конце.
"""
import io
import json
import os
import sys
import time

sys.path.insert(0, r"C:\sender\server")
import requests                                                # noqa: E402

ЖУРНАЛ = r"C:\sender\_ops\rotaciya-mobilnyh.jsonl"
МИНУТ = int(sys.argv[1]) if len(sys.argv) > 1 else 12
ШАГ = 20

прокси = []
видели = set()
for l in io.open(r"C:\sender\proxies-mobile.txt", encoding="utf-8",
                 errors="replace"):
    l = l.strip()
    if l and not l.startswith("#") and l not in видели:
        видели.add(l)
        прокси.append(l)

история = {i: [] for i in range(len(прокси))}
ж = io.open(ЖУРНАЛ, "a", encoding="utf-8")
до = time.time() + МИНУТ * 60
while time.time() < до:
    for i, url in enumerate(прокси):
        адрес = None
        try:
            r = requests.get("https://api.ipify.org",
                             proxies={"http": url, "https": url}, timeout=15)
            адрес = r.text.strip() if r.status_code == 200 else "код%s" % r.status_code
        except Exception as ex:                                # noqa: BLE001
            адрес = "ошибка"
        if not история[i] or история[i][-1][1] != адрес:
            история[i].append((time.strftime("%H:%M:%S"), адрес))
        ж.write(json.dumps({"когда": time.strftime("%H:%M:%S"),
                            "прокси": i + 1, "ip": адрес},
                           ensure_ascii=False) + "\n")
    ж.flush()
    os.fsync(ж.fileno())
    time.sleep(ШАГ)
ж.close()

print("=" * 74)
print("=== СВОДКА: РОТАЦИЯ МОБИЛЬНЫХ IP ===")
print("наблюдали %d минут, опрос каждые %d с" % (МИНУТ, ШАГ))
print("")
for i in range(len(прокси)):
    смены = история[i]
    print("прокси %d: разных адресов %d" % (i + 1, len(смены)))
    for когда, адрес in смены[:12]:
        print("   %s  %s" % (когда, адрес))
    if len(смены) >= 2:
        print("   -> IP МЕНЯЕТСЯ")
    else:
        print("   -> за время наблюдения IP не менялся")
