# -*- coding: utf-8 -*-
"""Чем основной сервер может проверять адреса: конфиг, DNS, 25-й порт.

Владелец 12.10: работник на VPS удалён (не оплачен), значит тяжёлую
SMTP-пробу теперь должен делать сам сервер. Прежде чем гнать партию,
выясняем: где лежит конфиг, видит ли сервер MX и пускает ли его сеть
наружу по 25-му порту.
"""
import os
import socket
import sys
import time

sys.path.insert(0, r"C:\sender")

print("--- конфиги рядом ---")
for к in os.listdir(r"C:\sender"):
    if к.lower().endswith((".yaml", ".yml")):
        п = os.path.join(r"C:\sender", к)
        print("   %-26s %8d байт" % (к, os.path.getsize(п)))

from sender.config import Config                                 # noqa: E402
cfg = None
for к in (r"C:\sender\sender.yaml", r"C:\sender\config.yaml"):
    try:
        cfg = Config.load(к)
        print("конфиг прочитан: %s" % к)
        break
    except Exception as e:  # noqa: BLE001
        print("   %s -> %s" % (к, str(e)[:70]))
if cfg is None:
    sys.exit(0)

from sender.addr_probe import AddrProbe, build_addr_probe        # noqa: E402

for ключ in ("validation.smtp_probe", "addr_probe.enabled",
             "addr_probe.helo", "addr_probe.mail_from",
             "addr_probe.worker_only", "probe_sync.enabled"):
    try:
        print("   %-26s = %r" % (ключ, cfg.get(ключ, "(нет)")))
    except Exception as e:  # noqa: BLE001
        print("   %-26s ошибка %s" % (ключ, e))

проба = AddrProbe(r"C:\sender\sender.db",
                  helo=str(cfg.get("addr_probe.helo", "") or "mail.local"),
                  mail_from=str(cfg.get("addr_probe.mail_from", "")
                                or "probe@localhost"))
print("")
print("--- MX с этого сервера ---")
for дом in ("mail.ru", "yandex.ru", "prokompressor.ru"):
    t = time.time()
    mx = проба.mx_for(дом)
    print("   %-22s %-34s %.2f сек" % (дом, str(mx)[:34], time.time() - t))

print("")
print("--- пускает ли сеть 25-й порт наружу ---")
for хост in ("mxs.mail.ru", "mx.yandex.ru", "aspmx.l.google.com"):
    t = time.time()
    try:
        s = socket.create_connection((хост, 25), timeout=12)
        баннер = s.recv(200).decode("utf-8", "replace").strip()
        s.close()
        print("   %-22s ОТКРЫТ  %.1f сек  %s" % (хост, time.time() - t,
                                                 баннер[:60]))
    except Exception as e:  # noqa: BLE001
        print("   %-22s ЗАКРЫТ  %.1f сек  %s" % (хост, time.time() - t,
                                                 str(e)[:50]))
print("")
print("=== ЧЕМ СЕРВЕР МОЖЕТ ПРОВЕРЯТЬ ===")
