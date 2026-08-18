# -*- coding: utf-8 -*-
"""Порог отбивок в gates: посмотреть и поднять по команде владельца.

18.08 владелец: «подними пока до 10% баунсы, чтобы завтра прошли все домены
нормально». Слово «пока» здесь важное - это временная мера, чтобы завтра
работали все ящики, а не половина.

Что при этом теряется, честно: порог 2.5% - ранний сигнал. Провайдеры
начинают резать домен где-то с 3-5%, и гейт закрывал ящик РАНЬШЕ них. С
порогом 10% мы узнаём о беде позже провайдера. Два ящика, у которых сейчас
6% мёртвых (k.yashin@kompressor-expert.ru, a.balakirev@compressor-store.ru),
снова начнут слать - в этом и смысл команды.

Конфиг читается при СТАРТЕ процесса, поэтому правка вступит в силу с
перезапуском панели.

    python zapusk_svoego_skripta.py ops/porog_otbivok.py
    python zapusk_svoego_skripta.py ops/porog_otbivok.py --поднять 10
"""
import io
import re
import shutil
import sys
import time

sys.path.insert(0, r"C:\sender")
from sender.config import Config                                 # noqa: E402

ПУТЬ = r"C:\sender\sender.yaml"
ПОДНЯТЬ = "--поднять" in sys.argv
НОВЫЙ = next((float(a) for a in sys.argv[1:]
              if a.replace(".", "", 1).isdigit()), 10.0)
КЛЮЧИ = ("domain_bounce_pct", "mailbox_bounce_pct", "provider_bounce_pct")

т = io.open(ПУТЬ, encoding="utf-8").read()
c = Config.load(ПУТЬ).gates()
print("пороги сейчас (как их видит панель):")
for k in КЛЮЧИ:
    print(f"  {k:<22} {getattr(c, k, '—')}")
print(f"  {'domain_complaint_pct':<22} {c.domain_complaint_pct}  (не трогаем)")
print(f"  {'global_complaint_pct':<22} {c.global_complaint_pct}  (не трогаем)")
print(f"  {'min_volume':<22} {c.min_volume}")
print(f"  {'window_days':<22} {c.window_days}")

строки = []
for k in КЛЮЧИ:
    for m in re.finditer(rf"(?m)^(\s*){k}:\s*([0-9.]+)(.*)$", т):
        строки.append((k, m.group(0)))
print("\nстроки в файле:")
for k, s in строки:
    print(f"  {s.strip()}")
if len(строки) != len(КЛЮЧИ):
    print("ОТКАЗ: нашёл не все ключи ровно по одному разу")
    raise SystemExit(2)

if not ПОДНЯТЬ:
    print(f"\nсухой прогон. Поднять до {НОВЫЙ} — аргумент --поднять")
    raise SystemExit(0)

новый_текст = т
for k in КЛЮЧИ:
    новый_текст = re.sub(rf"(?m)^(\s*){k}:\s*[0-9.]+", rf"\g<1>{k}: {НОВЫЙ}",
                         новый_текст)
бэкап = ПУТЬ + f".bak-{int(time.time())}"
shutil.copy2(ПУТЬ, бэкап)
io.open(ПУТЬ, "w", encoding="utf-8", newline="").write(новый_текст)
print(f"\nзаписано, бэкап: {бэкап}")
try:
    c2 = Config.load(ПУТЬ).gates()
    print("пороги после правки:")
    for k in КЛЮЧИ:
        print(f"  {k:<22} {getattr(c2, k, '—')}")
    print(f"  жалобы не тронуты: домен {c2.domain_complaint_pct}, "
          f"глобально {c2.global_complaint_pct}")
except Exception as ex:                                          # noqa: BLE001
    shutil.copy2(бэкап, ПУТЬ)
    print(f"КОНФИГ НЕ ГРУЗИТСЯ, откатил: {str(ex)[:200]}")
    raise SystemExit(3)
print("\nвступит в силу при перезапуске панели: конфиг читается при старте")
