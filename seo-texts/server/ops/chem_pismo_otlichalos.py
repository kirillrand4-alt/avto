# -*- coding: utf-8 -*-
"""Чем тестовое письмо отличается от боевого: заголовки и настройки."""
import io
import re

т = io.open(r"C:\sender\sender.yaml", encoding="utf-8", errors="replace").read()
print("=== юр-настройки писем ===")
for с in т.splitlines():
    if re.search(r"list_unsub|unsub_base|tracking|base_url|dkim|spf", с, re.I):
        print("   " + с.rstrip()[:120])
