# -*- coding: utf-8 -*-
"""Отвечают ли модели 5.5 на нашем маршруте шлюза: один короткий вызов."""
import sys
import time
sys.path.insert(0, r"C:\sender")
from sender.review_lenses import default_caller  # noqa: E402

for м in ("claude-opus-5-5", "claude-sonnet-5-5", "claude-haiku-5-5"):
    t = time.time()
    try:
        т, ответила = default_caller(
            "Назови одним предложением, чем фотосепаратор полезен мукомольному "
            "заводу. Только факт, без рекламы.", max_tokens=200, model=м)
        print("%-20s ок за %.1f с, ответила %s: %s"
              % (м, time.time() - t, ответила, " ".join(т.split())[:120]))
    except Exception as e:  # noqa: BLE001
        print("%-20s СБОЙ за %.1f с: %s" % (м, time.time() - t, str(e)[:150]))
print("=== НОВЫЕ МОДЕЛИ ===")
