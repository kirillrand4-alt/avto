# -*- coding: utf-8 -*-
"""Работает ли в панели цикл приёма вердиктов — и с каким кодом.

Правка заслона лежит на диске, но питон читает модуль при СТАРТЕ процесса:
пока службу не перезапустили, приём вердиктов крутится по старому коду и
может снова стереть приговор. Здесь смотрим, есть ли кому его стирать.
"""
import os
import sys
import time

sys.path.insert(0, r"C:\sender")
from sender.config import Config                                 # noqa: E402
from sender.store import Store                                   # noqa: E402

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))

for ключ in ("probe_sync_enabled", "addr_probe_enabled", "auto_send_enabled"):
    print(f"{ключ}: {store.get_setting(ключ, '(нет)')}")
print("probe_sync.interval_sec:", cfg.get("probe_sync.interval_sec", "(нет)"))
print("addr_probe.interval_sec:", cfg.get("addr_probe.interval_sec", "(нет)"))

with store._lock:
    r = store._conn.execute(
        "SELECT verdict, source, ts FROM addr_probe WHERE email=?",
        ("kk@vebfabrika.ru",)).fetchone()
print("\nkk@vebfabrika.ru сейчас:", tuple(r) if r else "нет строки")

# Когда стартовала служба панели: если позже выкатки — код уже новый.
try:
    import subprocess
    o = subprocess.run(
        ["powershell", "-NoProfile", "-Command",
         "(Get-Process -Id (Get-WmiObject Win32_Service -Filter "
         "\"Name='SenderPanel'\").ProcessId).StartTime.ToString('o')"],
        capture_output=True, text=True, timeout=60)
    print("старт службы SenderPanel:", (o.stdout or o.stderr).strip()[:60])
except Exception as ex:                                          # noqa: BLE001
    print("старт службы: не спросить —", str(ex)[:80])

ф = r"C:\sender\sender\addr_probe.py"
print("файл addr_probe.py изменён:",
      time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(os.path.getmtime(ф))))
