# -*- coding: utf-8 -*-
"""Убрать мёртвый legal.unsub_base_url (указывает на домен, помеченный
Касперским). Сейчас он инертен — выключатель legal.unsub_http_enabled не
выставлен, — но включи кто-нибудь выключатель, и в письма уедет ссылка на
несуществующий хост помеченного домена.

Сначала смотрим, КАКОЙ файл читает живая служба: конфигов на сервере два.
"""
import io
import os
import sys
import time

sys.path.insert(0, r"C:\sender")
КАТИТЬ = "--katit" in sys.argv
КАНДИДАТЫ = [r"C:\sender\sender.yaml", r"C:\sender\config.yaml"]

for п in КАНДИДАТЫ:
    if not os.path.exists(п):
        print("%s — нет файла" % п)
        continue
    т = io.open(п, encoding="utf-8").read()
    строки = [(i + 1, с) for i, с in enumerate(т.split("\n"))
              if "unsub" in с.lower()]
    print("=== %s (%d знаков, изменён %s) ==="
          % (п, len(т), time.strftime("%Y-%m-%d %H:%M",
                                      time.localtime(os.path.getmtime(п)))))
    for н, с in строки:
        print("   %4d| %s" % (н, с.rstrip()))
    if not строки:
        print("   про unsub ничего")

print()
from sender.config import Config                                   # noqa: E402
for п in КАНДИДАТЫ:
    if not os.path.exists(п):
        continue
    try:
        c = Config.load(п)
        print("%s → unsub_base_url=%r, unsub_http_enabled=%r"
              % (os.path.basename(п), c.get("legal.unsub_base_url", None),
                 c.get("legal.unsub_http_enabled", None)))
    except Exception as ex:
        print("%s → не читается: %s" % (os.path.basename(п), ex))

if not КАТИТЬ:
    print("\n[сухой прогон] с --katit уберу строку из обоих файлов, где она есть")
    raise SystemExit(0)

for п in КАНДИДАТЫ:
    if not os.path.exists(п):
        continue
    было = io.open(п, encoding="utf-8").read()
    строки = было.split("\n")
    цель = [с for с in строки if с.strip().startswith("unsub_base_url:")]
    if len(цель) != 1:
        print("%s: строк unsub_base_url — %d, не трогаю" % (п, len(цель)))
        continue
    бэк = п + ".bak-%d" % int(time.time())
    with io.open(бэк, "w", encoding="utf-8", newline="") as f:
        f.write(было); f.flush(); os.fsync(f.fileno())
    стало = "\n".join(с for с in строки if с is not цель[0])
    with io.open(п, "w", encoding="utf-8", newline="") as f:
        f.write(стало); f.flush(); os.fsync(f.fileno())
    try:
        c = Config.load(п)
        print("%s: убрано, конфиг читается, unsub_base_url=%r (бэкап %s)"
              % (os.path.basename(п), c.get("legal.unsub_base_url", None),
                 os.path.basename(бэк)))
    except Exception as ex:
        with io.open(п, "w", encoding="utf-8", newline="") as f:
            f.write(было); f.flush(); os.fsync(f.fileno())
        print("%s: конфиг перестал читаться, ОТКАТИЛ: %s" % (п, ex))
