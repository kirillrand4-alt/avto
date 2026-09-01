# -*- coding: utf-8 -*-
"""Только чтение: кривая прогрева из sender/ramp.py + ручные потолки."""
import io
import json
import sys

print("=== sender/ramp.py ===")
try:
    t = io.open(r"C:\sender\sender\ramp.py", encoding="utf-8", errors="replace").read()
    for i, x in enumerate(t.splitlines()[:70]):
        print("  %3d  %s" % (i + 1, x[:110]))
except Exception as ex:
    print("  ", str(ex)[:90])

sys.path.insert(0, r"C:\sender")
from sender.config import Config  # noqa: E402
from sender.store import Store    # noqa: E402
from sender.ramp import daily_send_limit  # noqa: E402

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))

print("\n=== РУЧНЫЕ ПОТОЛКИ (panel_settings.send_limits) ===")
try:
    v = store.get_setting("send_limits")
    print("  " + json.dumps(v, ensure_ascii=False)[:600] if v else "  не задано")
except Exception as ex:
    print("  ", str(ex)[:90])

print("\n=== ИТОГ: КРИВАЯ ПО ДНЯМ РАМПЫ ===")
print("  %5s %10s %10s" % ("день", "yandex", "mailru"))
for d in (0, 1, 2, 3, 4, 5, 7, 9, 10, 11, 14, 15, 18, 21, 22, 30):
    try:
        y = daily_send_limit(cfg, "yandex", d)
        m = daily_send_limit(cfg, "mailru", d)
        print("  %5d %10s %10s" % (d, y, m))
    except Exception as ex:
        print("  %5d  ошибка %s" % (d, str(ex)[:50]))
