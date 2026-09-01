# -*- coding: utf-8 -*-
"""Только чтение: какая функция считает reply+reply_auto вместе."""
import io
import re

стр = io.open(r"C:\sender\sender\store.py", encoding="utf-8",
              errors="replace").read().splitlines()
for ц in (2801, 2206, 2015):
    # назад до ближайшего def
    i = ц - 1
    while i > 0 and not re.match(r"\s*def ", стр[i]):
        i -= 1
    print("=== строка %d относится к %s ===" % (ц, стр[i].strip()[:70]))
    for j in range(i, min(i + 16, len(стр))):
        print("  %4d  %s" % (j + 1, стр[j][:104]))
    print("  ...")
    print("  %4d  %s" % (ц, стр[ц - 1][:104]))
    print()

print("=== ИТОГ ===")
print("  analytics.EVENT_REPLY = 'reply' — экран «Динамика 7 дней» считает ТОЛЬКО его")
print("  функции выше считают reply и reply_auto вместе")
