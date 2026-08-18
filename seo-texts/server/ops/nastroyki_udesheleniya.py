# -*- coding: utf-8 -*-
"""Включить удешевление генерации и перелив между пулами — ключи в sender.yaml.

  ai_quota.best_of          3 -> 2   вариантов письма на выбор судье
  ai_quota.checker_model    ""-> claude-sonnet-4-6   судья/верификатор/линза
  provider_split.overflow   нет -> true              перелив в чужой пул
  provider_split.overflow_max_bounce_pct -> 3.0      только чистые ящики

Конфиг читается при СТАРТЕ процесса: правка вступит в силу с перезапуском
панели. Пишем с бэкапом и проверяем, что после правки конфиг грузится.

    python zapusk_svoego_skripta.py ops/nastroyki_udesheleniya.py
    python zapusk_svoego_skripta.py ops/nastroyki_udesheleniya.py --писать
"""
import io
import re
import shutil
import sys
import time

sys.path.insert(0, r"C:\sender")
from sender.config import Config                                 # noqa: E402

ПУТЬ = r"C:\sender\sender.yaml"
ПИСАТЬ = "--писать" in sys.argv

т = io.open(ПУТЬ, encoding="utf-8").read()
c = Config.load(ПУТЬ)
print("сейчас:")
print(f"  ai_quota.best_of        {c.get('ai_quota.best_of', '(нет ключа)')}")
print(f"  ai_quota.checker_model  {c.get('ai_quota.checker_model', '(нет ключа)')}")
print(f"  provider_split.overflow {c.get('provider_split.overflow', '(нет ключа)')}")
print(f"  overflow_max_bounce_pct "
      f"{c.get('provider_split.overflow_max_bounce_pct', '(нет ключа)')}")

новый = т
# ai_quota: ключ может уже быть или нет
if re.search(r"(?m)^ai_quota:", новый):
    if not re.search(r"(?m)^\s+best_of:", новый):
        новый = re.sub(r"(?m)^(ai_quota:.*)$",
                       r"\1\n  best_of: 2", новый, count=1)
    else:
        новый = re.sub(r"(?m)^(\s+)best_of:\s*\d+", r"\g<1>best_of: 2", новый)
    if not re.search(r"(?m)^\s+checker_model:", новый):
        новый = re.sub(r"(?m)^(ai_quota:.*)$",
                       r"\1\n  checker_model: claude-sonnet-4-6", новый, count=1)
else:
    новый += "\n\nai_quota:\n  best_of: 2\n  checker_model: claude-sonnet-4-6\n"

if re.search(r"(?m)^provider_split:", новый):
    if not re.search(r"(?m)^\s+overflow:", новый):
        новый = re.sub(
            r"(?m)^(provider_split:.*)$",
            r"\1\n  # перелив в чужой пул, когда свой выбрал лимит (18.08)\n"
            r"  overflow: true\n  overflow_max_bounce_pct: 3.0", новый, count=1)
else:
    новый += ("\n\nprovider_split:\n  overflow: true\n"
              "  overflow_max_bounce_pct: 3.0\n")

if новый == т:
    print("\nвсё уже стоит, менять нечего")
    raise SystemExit(0)
print(f"\nизменится байт: {len(новый) - len(т):+d}")
if not ПИСАТЬ:
    print("сухой прогон: файл не тронут. Писать — аргумент --писать")
    raise SystemExit(0)

бэкап = ПУТЬ + f".bak-{int(time.time())}"
shutil.copy2(ПУТЬ, бэкап)
io.open(ПУТЬ, "w", encoding="utf-8", newline="").write(новый)
try:
    c2 = Config.load(ПУТЬ)
except Exception as ex:                                          # noqa: BLE001
    shutil.copy2(бэкап, ПУТЬ)
    print(f"КОНФИГ НЕ ГРУЗИТСЯ, откатил: {str(ex)[:200]}")
    raise SystemExit(3)
print(f"записано, бэкап: {бэкап}")
print("стало:")
print(f"  ai_quota.best_of        {c2.get('ai_quota.best_of')}")
print(f"  ai_quota.checker_model  {c2.get('ai_quota.checker_model')}")
print(f"  provider_split.overflow {c2.get('provider_split.overflow')}")
print(f"  overflow_max_bounce_pct "
      f"{c2.get('provider_split.overflow_max_bounce_pct')}")
print("\nвступит в силу при перезапуске панели")
