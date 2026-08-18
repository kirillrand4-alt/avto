# -*- coding: utf-8 -*-
"""Сверить target_gate.py на сервере с тем, что я собираюсь выкатить.

Правило деплоя: C:\\sender\\sender\\ делится с соседней сессией, поэтому
сначала сверяем sha256, а не перезаписываем вслепую.
"""
import hashlib
import io
import os
p = r"C:\sender\sender\target_gate.py"
if not os.path.exists(p):
    print("на сервере файла нет")
else:
    d = io.open(p, "rb").read()
    print("sha256:", hashlib.sha256(d).hexdigest())
    print("байт:", len(d))
    t = d.decode("utf-8", "replace")
    print("минус_класс уже есть:", "минус_класс" in t)
    print("больницы в промпте продавца:", "больницы и лаборатории" in t)
