# -*- coding: utf-8 -*-
"""Какую ошибку шлюз отдаёт на модели 5.5 — один вызов без запасной."""
import sys
import time
sys.path.insert(0, r"C:\sender")
import gen_provider  # noqa: E402

for м in ("claude-opus-5-5", "claude-sonnet-5-5", "claude-opus-4-8"):
    t = time.time()
    try:
        о = gen_provider.call(None, [{"role": "user", "content":
                                      "Скажи одно слово: работает"}],
                              model=м, attempts=1, thinking=False)
        print("%-18s ок %.1f с: %s" % (м, time.time() - t,
                                      str(getattr(о, "text", о))[:80]))
    except Exception as e:  # noqa: BLE001
        print("%-18s ОШИБКА %.1f с: %s" % (м, time.time() - t, str(e)[:260]))
print("=== ОШИБКА 5.5 ===")
