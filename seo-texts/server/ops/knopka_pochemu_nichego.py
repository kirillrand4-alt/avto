# -*- coding: utf-8 -*-
"""Кнопка «Сгенерировать в очередь» нажата, а писем нет: где именно оборвалось.

Владелец нажал кнопку с числом 14 на группе «Партия 935» (6 892) - и ничего
не началось. Причин ровно три, и они различимы замером:

  1. кандидатов ноль - отбор ничего не нашёл (тогда генерация и не
     начиналась, и это НЕ ошибка кнопки);
  2. кандидаты есть, но отбор идёт слишком долго - запрос панели отваливается
     по таймауту раньше, чем дойдёт до модели (store.recipient_groups читает
     ВСЮ таблицу получателей на каждый вызов);
  3. отбор упал с ошибкой.

Печатаем: сколько секунд идёт отбор, сколько нашлось, и первые кандидаты.
Ничего не генерируем - только меряем.

    python zapusk_svoego_skripta.py ops/knopka_pochemu_nichego.py 10 14
"""
import sys
import time
import traceback

sys.path.insert(0, r"C:\sender")
from sender.ai_quota import build_ai_quota                      # noqa: E402
from sender.config import Config                                # noqa: E402
from sender.store import Store                                  # noqa: E402

КАМПАНИЯ = int(sys.argv[1]) if len(sys.argv) > 1 else 10
СКОЛЬКО = int(sys.argv[2]) if len(sys.argv) > 2 else 14

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
q = build_ai_quota(store, cfg)

т0 = time.time()
try:
    группы = store.recipient_groups()
    по_id = группы.get("по_id") or {}
    print(f"recipient_groups: {time.time() - т0:.1f}с, строк {len(по_id)}")
except Exception:                                               # noqa: BLE001
    print("recipient_groups упал:")
    traceback.print_exc()
    raise SystemExit(1)

camp = store.get_campaign(КАМПАНИЯ)
print(f"кампания {КАМПАНИЯ}: name={getattr(camp, 'name', None)!r} "
      f"status={getattr(camp, 'status', None)!r}")
try:
    import json as _j
    кон = getattr(camp, "config_json", None)
    if кон:
        d = _j.loads(кон) if isinstance(кон, str) else кон
        print(f"  config: {_j.dumps(d, ensure_ascii=False)[:400]}")
except Exception as ex:                                         # noqa: BLE001
    print("  config не разобрался:", str(ex)[:120])

т1 = time.time()
try:
    канд = q.candidates(КАМПАНИЯ, СКОЛЬКО)
    print(f"\ncandidates({КАМПАНИЯ}, {СКОЛЬКО}): {time.time() - т1:.1f}с, "
          f"нашлось {len(канд)}")
    for c in канд[:10]:
        e = getattr(c, "email", None) or (c.get("email")
                                          if isinstance(c, dict) else c)
        n = getattr(c, "company_name", None) or (
            c.get("company_name") if isinstance(c, dict) else "")
        print(f"  {str(e)[:40]:<42} {str(n)[:44]}")
except Exception:                                               # noqa: BLE001
    print(f"\ncandidates упал через {time.time() - т1:.1f}с:")
    traceback.print_exc()

print(f"\nвсего {time.time() - т0:.1f}с")
