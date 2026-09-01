# -*- coding: utf-8 -*-
"""Только чтение: store.last_sent_mailbox — что он читает и что вернёт сейчас."""
import io
import re
import sys

стр = io.open(r"C:\sender\sender\store.py", encoding="utf-8",
              errors="replace").read().splitlines()
н = [i for i, x in enumerate(стр) if re.search(r"def last_sent_mailbox", x)]
print("=== store.last_sent_mailbox ===")
for i in н:
    for j in range(i, min(i + 26, len(стр))):
        print("  %4d  %s" % (j + 1, стр[j][:110]))

sys.path.insert(0, r"C:\sender")
from sender.config import Config  # noqa: E402
from sender.store import Store    # noqa: E402
cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))

print("\n=== ИТОГ ===")
try:
    v = store.last_sent_mailbox()
    print("  last_sent_mailbox() сейчас возвращает: %r" % v)
except Exception as ex:
    print("  ошибка: %s" % str(ex)[:100])
пулы = cfg.provider_pools() or {}
for имя, я in пулы.items():
    print("  пул %-14s %d ящиков; a.erokhin в нём: %s"
          % (имя, len(я), "a.erokhin@food-sort.ru" in list(я)))
    if имя == "pool_yandex":
        print("     порядок пула: %s" % ", ".join(list(я)[:30]))
