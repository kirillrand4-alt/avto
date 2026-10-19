# -*- coding: utf-8 -*-
"""Строки запусков из лога генерации КЦ «Россия 9000»: какой моделью и с какими флагами."""
import io
for s in io.open(r"C:\sender\_ops\gen-kc-9000.log", encoding="utf-8", errors="replace"):
    if "ЗАПУСК" in s or s.startswith("итог:"):
        print(s.rstrip()[:200])
