# -*- coding: utf-8 -*-
"""Где лежит ключ провайдера: какие файлы содержат СТРОКУ с именем PROVIDER_API_KEY и есть ли он в окружении процесса.
Значения НЕ печатаются, только да/нет."""
import os
for п in (r"C:\sender\server\.env", r"C:\sender\.env", r"C:\sender\panel.env", r"C:\seostat\.env"):
    if os.path.exists(п):
        есть = any(с.strip().startswith("PROVIDER_API_KEY") for с in open(п, encoding="utf-8-sig", errors="replace"))
        print("%-28s файл есть, PROVIDER_API_KEY: %s" % (п, "да" if есть else "нет"))
    else:
        print("%-28s файла нет" % п)
print("в окружении процесса (служба):", "да" if os.environ.get("PROVIDER_API_KEY") else "нет")
print("PROVIDER_BASE_URL в окружении:", "да" if os.environ.get("PROVIDER_BASE_URL") else "нет")
