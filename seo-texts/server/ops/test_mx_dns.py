# -*- coding: utf-8 -*-
"""Проверка, отвечает ли DNS на MX-запросы (dnspython, nslookup системный и 8.8.8.8). Только чтение.
   test_mx_dns.py [--stop=PID] — заодно остановить процесс перепробы."""
import subprocess, sys
for x in sys.argv:
    if x.startswith("--stop="):
        print(subprocess.run(["taskkill", "/PID", x.split("=")[1], "/F"], capture_output=True, text=True, errors="replace").stdout.strip())
try:
    import dns.resolver
    print("dnspython mail.ru:", [str(r.exchange) for r in dns.resolver.resolve("mail.ru", "MX", lifetime=10)][:2])
except Exception as ex: print("dnspython:", repr(ex)[:200])
for арг in (["nslookup", "-type=MX", "mail.ru"], ["nslookup", "-type=MX", "mail.ru", "8.8.8.8"]):
    r = subprocess.run(арг, capture_output=True, text=True, timeout=25, errors="replace")
    print(" ".join(арг[3:]) or "системный", "->", (r.stdout + r.stderr).replace("\n", " | ")[:300])
