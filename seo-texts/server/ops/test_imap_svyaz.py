# -*- coding: utf-8 -*-
"""Скорость TLS-соединения с imap.yandex.ru:993 и smtp.yandex.ru:465 (5 попыток), без входа. Маршрут до них. Только чтение."""
import socket, ssl, subprocess, time
ctx = ssl.create_default_context()
for хост, порт in (("imap.yandex.ru", 993), ("smtp.yandex.ru", 465)):
    рез = []
    for _ in range(5):
        т = time.time()
        try:
            with socket.create_connection((хост, порт), timeout=20) as s, ctx.wrap_socket(s, server_hostname=хост): рез.append("%.1fс" % (time.time() - т))
        except Exception as ex: рез.append("СБОЙ %s за %.0fс" % (type(ex).__name__, time.time() - т))
    print(хост, порт, рез)
ip = socket.gethostbyname("imap.yandex.ru")
print("imap.yandex.ru ->", ip, "| маршрут:", subprocess.run(["powershell", "-NoProfile", "-Command", "Find-NetRoute -RemoteIPAddress %s | Select -Expand InterfaceAlias -First 2" % ip],
      capture_output=True, text=True, errors="replace").stdout.split())
