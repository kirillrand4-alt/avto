# -*- coding: utf-8 -*-
"""Настройки пробы из конфига (без секретов): helo, mail_from, source_ip; IP-адреса сервера; PTR каждого. Только чтение."""
import socket, subprocess, sys
sys.path.insert(0, r"C:\sender")
from sender.config import Config
import os
for п in (r"C:\sender\config.yaml", r"C:\sender\sender.yaml"):
    if os.path.exists(п):
        print("== конфиг", п); _c = Config.load(п)
        for к in ("addr_probe.helo", "addr_probe.mail_from", "addr_probe.source_ip", "addr_probe.enabled"): print("  ", к, "=", _c.get(к, None))
cfg = Config.load(r"C:\sender\sender.yaml")
for к in ("addr_probe.helo", "addr_probe.mail_from", "addr_probe.source_ip", "addr_probe.per_domain", "addr_probe.pause_sec"):
    print(к, "=", cfg.get(к, None))
вых = subprocess.run(["powershell", "-NoProfile", "-Command", "Get-NetIPAddress -AddressFamily IPv4 | Select -Expand IPAddress"], capture_output=True, text=True).stdout
for ip in вых.split():
    try: ptr = socket.gethostbyaddr(ip)[0]
    except Exception as ex: ptr = "нет (%s)" % ex
    print("IP", ip, "PTR:", ptr)
h = cfg.get("addr_probe.helo", "") or ""
if h:
    try: print("A-запись helo:", h, socket.gethostbyname_ex(h))
    except Exception as ex: print("helo не резолвится:", ex)
