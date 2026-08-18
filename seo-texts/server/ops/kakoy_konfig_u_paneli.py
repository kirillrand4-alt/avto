# -*- coding: utf-8 -*-
"""Каким конфигом живёт панель — и совпадает ли он с тем, что я мерил.

Служба запускается как `python -m sender serve-api` БЕЗ --config, значит
путь берётся из умолчания или из переменной SENDER_CONFIG. Я всё это время
читал C:\\sender\\sender.yaml. Если панель читает другой файл, мои замеры
лимитов и окна относятся не к той панели.
"""
import hashlib
import io
import os
import sys

sys.path.insert(0, r"C:\sender")

пути = [r"C:\sender\sender.yaml", r"C:\sender\config.yaml",
        os.environ.get("SENDER_CONFIG", "")]
for п in пути:
    if not п:
        continue
    if not os.path.exists(п):
        print(f"{п}: НЕТ ФАЙЛА")
        continue
    b = io.open(п, "rb").read()
    print(f"{п}: {len(b)} байт sha256={hashlib.sha256(b).hexdigest()[:16]}")

print(f"\nSENDER_CONFIG в окружении этого процесса: "
      f"{os.environ.get('SENDER_CONFIG', '(нет)')}")

# что говорит сам модуль про путь по умолчанию
try:
    import sender.config as C
    for имя in dir(C):
        if "DEFAULT" in имя.upper() or "PATH" in имя.upper():
            print(f"  sender.config.{имя} = {getattr(C, имя)!r}")
except Exception as ex:                                          # noqa: BLE001
    print("config:", str(ex)[:100])

# и что в каждом файле по ключевым настройкам
from sender.config import Config                                  # noqa: E402
for п in [x for x in пути if x and os.path.exists(x)]:
    try:
        c = Config.load(п)
    except Exception as ex:                                      # noqa: BLE001
        print(f"\n{п}: не грузится — {str(ex)[:100]}")
        continue
    print(f"\n=== {п}")
    print(f"  service.db_path: {c.get('service.db_path', '(нет)')}")
    print(f"  confirm.live_send: {c.get('confirm.live_send', '(нет)')}")
    try:
        print(f"  ramp yandex: {c.ramp_curve('yandex')}")
        print(f"  ramp mailru: {c.ramp_curve('mailru')}")
    except Exception as ex:                                      # noqa: BLE001
        print(f"  ramp: {str(ex)[:60]}")
    print(f"  ящиков: {len(c.mailboxes())}")
    w = c.sending_window()
    print(f"  окно: {w.days} {w.start}-{w.end} {w.tz}")
    print(f"  provider_split.routing: {c.get('provider_split.routing', '(нет)')}")
