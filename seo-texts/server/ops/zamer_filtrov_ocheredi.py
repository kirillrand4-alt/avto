# -*- coding: utf-8 -*-
"""Что именно съедает время на экране подтверждения, кроме выборки."""
import json, sys, time
sys.path.insert(0, r"C:\sender")
from sender.config import Config                                # noqa: E402
from sender.confirm import ConfirmSend                          # noqa: E402
from sender.store import Store                                  # noqa: E402
from sender.suppression import Suppression                      # noqa: E402

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
cs = ConfirmSend(cfg, store, Suppression(store))

т = time.time(); rows = cs.pending(campaign_id=None, limit=100000, offset=0)
print("   pending(100000)          %6.2f с  (%d строк)" % (time.time() - т, len(rows)))

т = time.time()
try:
    карта = store.recipient_mx_map()
    n = len(карта.get("по_id") or {})
except Exception as ex:                                         # noqa: BLE001
    карта, n = {}, "ошибка: " + str(ex)[:50]
print("   recipient_mx_map()       %6.2f с  (%s записей)" % (time.time() - т, n))

т = time.time()
try:
    гр = store.recipient_groups()
    n = len(гр.get("по_id") or {})
except Exception as ex:                                         # noqa: BLE001
    n = "ошибка: " + str(ex)[:50]
print("   recipient_groups()       %6.2f с  (%s записей)" % (time.time() - т, n))

getter = getattr(cs, "letter_division", None)
т = time.time()
к = 0
if callable(getter):
    for r in rows:
        try:
            getter(r)
        except Exception:                                       # noqa: BLE001
            pass
        к += 1
print("   letter_division x%-6d  %6.2f с" % (к, time.time() - т))

т = time.time()
_ = sorted(rows, key=lambda r: -float(((r.get("panel") or {}).get("score")
                                       or {}).get("score") or -1))
print("   сортировка по score      %6.2f с" % (time.time() - т))

т = time.time()
кусок = json.dumps(rows[:50], ensure_ascii=False, default=str)
print("   сериализация 50 карточек %6.2f с  (%.1f КБ)"
      % (time.time() - т, len(кусок) / 1024.0))
print("")
print("=" * 70)
print("=== ГДЕ ВРЕМЯ ЭКРАНА ПОДТВЕРЖДЕНИЯ ===")
