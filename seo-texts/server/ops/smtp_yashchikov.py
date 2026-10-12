# -*- coding: utf-8 -*-
"""SMTP каждого ящика Meyer: хост, порт и соединение прямо сейчас.

Письма кампании 14 падают на ящике v.kuzmin@inspection-systems.ru с
таймаутом соединения. Проверяем все Meyer-ящики: какой у них сервер,
отвечает ли он с основного сервера на SMTP-порт и на 465/587/25.
"""
import socket
import sys
import time

sys.path.insert(0, r"C:\sender")
from sender.config import Config                                 # noqa: E402

cfg = Config.load(r"C:\sender\sender.yaml")
ящики = cfg.get("mailboxes", ()) or ()


def пробить(хост, порт):
    t = time.time()
    try:
        s = socket.create_connection((хост, порт), timeout=10)
        s.close()
        return "ОК %.1fс" % (time.time() - t)
    except Exception as e:  # noqa: BLE001
        return "СБОЙ %.0fс %s" % (time.time() - t, type(e).__name__)


def поле(м, к, умолч=None):
    return (м.get(к, умолч) if hasattr(м, "get") else getattr(м, к, умолч))


print("ящиков в конфиге: %d" % len(ящики))
виденные = {}
for м in ящики:
    ид = str(поле(м, "mailbox_id") or поле(м, "id") or "")
    хост = str(поле(м, "smtp_host") or "")
    порт = int(поле(м, "smtp_port") or 465)
    if str(поле(м, "division") or "") != "meyer" and "inspection" not in ид:
        continue
    ключ = (хост, порт)
    if ключ not in виденные:
        try:
            ip = socket.gethostbyname(хост)
        except Exception as e:  # noqa: BLE001
            ip = "DNS-сбой %s" % type(e).__name__
        виденные[ключ] = (ip, пробить(хост, порт))
    ip, итог = виденные[ключ]
    print("   %-36s пул=%-14s %s:%d (%s) -> %s"
          % (ид[:36], поле(м, "pool"), хост, порт, ip, итог))
print("")
print("--- тот же хост на других портах ---")
for (хост, порт) in виденные:
    for п in (25, 465, 587):
        if п != порт:
            print("   %s:%d -> %s" % (хост, п, пробить(хост, п)))
print("")
print("--- для сравнения: внешние SMTP ---")
for хост, п in (("smtp.yandex.ru", 465), ("smtp.mail.ru", 465),
                ("smtp.gmail.com", 465)):
    print("   %s:%d -> %s" % (хост, п, пробить(хост, п)))
print("=== SMTP ЯЩИКОВ ===")
