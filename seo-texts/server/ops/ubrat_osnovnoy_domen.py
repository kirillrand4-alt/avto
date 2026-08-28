# -*- coding: utf-8 -*-
"""Основной домен компании — вон из рассыльщика (команда владельца 28.08).

prokompressor.ru — сайт, на котором стоит бизнес. Репутацию рассылки он
делить не должен: ни ссылкой в письме, ни доменом отписки, ни трекингом.

В legal.unsub_base_url ключ обязателен (_build_legal валидирует как http(s)),
поэтому вместо домена ставим адрес в зарезервированной зоне .invalid — она по
RFC 2606 не может быть зарегистрирована и не резолвится никогда. Если кто-то
включит HTTP-отписку, ссылка сломается заметно и НИ ОДИН наш домен под
чужой трафик не попадёт.
"""
import io
import os
import re
import sys
import time

sys.path.insert(0, r"C:\sender")
КАТИТЬ = "--katit" in sys.argv
ПУТЬ = r"C:\sender\sender.yaml"
СТАРОЕ = '  unsub_base_url: "https://prokompressor.ru/u"\n'
НОВОЕ = '  unsub_base_url: "https://unsub.invalid/u"\n'

т = io.open(ПУТЬ, encoding="utf-8").read()
print("=== где в конфиге встречается основной домен ===")
нашли = [(i + 1, с.strip()) for i, с in enumerate(т.split("\n"))
         if "prokompressor" in с.lower()]
for н, с in нашли:
    print("   %4d| %s" % (н, с[:110]))
if not нашли:
    print("   нигде")

print("\n=== где он встречается в КОДЕ отправки и генерации ===")
корни = [r"C:\sender\sender"]
for корень in корни:
    for путь, кат, файлы in os.walk(корень):
        кат[:] = [d for d in кат if d not in ("__pycache__", "web", "tests")]
        for имя in файлы:
            if not имя.endswith(".py"):
                continue
            п = os.path.join(путь, имя)
            текст = io.open(п, encoding="utf-8", errors="ignore").read()
            for i, с in enumerate(текст.split("\n")):
                if "prokompressor" in с.lower():
                    вид = "комментарий" if с.strip().startswith("#") else "КОД"
                    print("   %-22s:%-5d %-12s %s"
                          % (имя, i + 1, вид, с.strip()[:90]))

if not КАТИТЬ:
    print("\n[сухой прогон] с --katit заменю значение отписки")
    raise SystemExit(0)

if т.count(СТАРОЕ) != 1:
    print("\nякорь найден %d раз — не трогаю" % т.count(СТАРОЕ))
    raise SystemExit(1)
было = т
т = т.replace(СТАРОЕ, НОВОЕ).replace(
    "  # значение уведено на настоящий сайт компании, а HTTP-канал отписки\n",
    "  # значение уведено в зарезервированную зону .invalid (RFC 2606): она не\n"
    "  # резолвится никогда. Основной домен компании в рассыльщике не\n"
    "  # используется вовсе — команда владельца 28.08. HTTP-канал отписки\n")
бэк = ПУТЬ + ".bak-%d" % int(time.time())
with io.open(бэк, "w", encoding="utf-8", newline="") as f:
    f.write(было); f.flush(); os.fsync(f.fileno())
with io.open(ПУТЬ, "w", encoding="utf-8", newline="") as f:
    f.write(т); f.flush(); os.fsync(f.fileno())
from sender.config import Config                                   # noqa: E402
try:
    c = Config.load(ПУТЬ)
    print("\nконфиг читается, unsub_base_url = %r" % c.legal().unsub_base_url)
    print("бэкап: %s" % os.path.basename(бэк))
except Exception as ex:
    with io.open(ПУТЬ, "w", encoding="utf-8", newline="") as f:
        f.write(было); f.flush(); os.fsync(f.fileno())
    print("\nконфиг не читается, ОТКАТИЛ: %s" % ex)
    raise SystemExit(1)
осталось = [(i + 1, с.strip()) for i, с in enumerate(т.split("\n"))
            if "prokompressor" in с.lower()]
print("основной домен в конфиге после правки: %s"
      % ("; ".join("стр.%d %s" % (н, с[:60]) for н, с in осталось) or "нигде"))
