# -*- coding: utf-8 -*-
"""Значение ключа конфига панели (только чтение; секреты не печатаем):
    konfig_klyuch.py <ключ.через.точку>"""
import sys
sys.path.insert(0, r"C:\sender")
from sender.config import Config  # noqa: E402
к = sys.argv[1]
if any(s in к.lower() for s in ("pass", "token", "key", "secret")):
    sys.exit("секретный ключ не печатаю")
for путь in (r"C:\sender\sender.yaml", r"C:\sender\config.yaml"):
    try:
        print(путь, "->", Config.load(путь).get(к, "НЕТ КЛЮЧА"))
    except Exception as ex:  # noqa: BLE001
        print(путь, "не читается:", str(ex)[:100])
