# -*- coding: utf-8 -*-
"""Весь ли Яндекс недоступен с сервера или только почтовый узел."""
import socket
import time


def пробить(хост, порт, ip=None):
    t = time.time()
    try:
        s = socket.create_connection((ip or хост, порт), timeout=8)
        s.close()
        return "ОК %.1fс" % (time.time() - t)
    except Exception as e:  # noqa: BLE001
        return "СБОЙ %.0fс %s" % (time.time() - t, type(e).__name__)


for хост in ("smtp.yandex.ru", "smtp.yandex.com", "mx.yandex.ru"):
    try:
        ips = sorted({a[4][0] for a in socket.getaddrinfo(хост, None, socket.AF_INET)})
    except Exception as e:  # noqa: BLE001
        ips = []
        print("%s: DNS сбой %s" % (хост, e))
    for ip in ips:
        порт = 25 if хост.startswith("mx") else 465
        print("   %-18s %-16s :%-3d %s" % (хост, ip, порт, пробить(хост, порт, ip)))
for хост, порт in (("yandex.ru", 443), ("ya.ru", 443), ("imap.yandex.ru", 993),
                   ("smtp.mail.ru", 465), ("router.cheap", 443),
                   ("api.anthropic.com", 443)):
    print("   %-18s %-16s :%-3d %s" % (хост, "", порт, пробить(хост, порт)))
print("=== ДОСТУП К ЯНДЕКСУ ===")
