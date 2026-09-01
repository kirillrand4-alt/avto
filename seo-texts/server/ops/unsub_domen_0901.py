# -*- coding: utf-8 -*-
"""Только чтение: на какой домен ведёт отписка."""
import sys

sys.path.insert(0, r"C:\sender")
from sender.config import Config  # noqa: E402
cfg = Config.load(r"C:\sender\sender.yaml")
try:
    legal = cfg.legal()
    for п in dir(legal):
        if п.startswith("_"):
            continue
        v = getattr(legal, п)
        if not callable(v):
            print("  legal.%-20s = %r" % (п, str(v)[:110]))
except Exception as ex:
    print("  legal(): %s" % str(ex)[:90])
print("\n=== ИТОГ ===")
try:
    u = cfg.legal().unsub_base_url
    d = str(u).split("//", 1)[-1].split("/")[0]
    print("  адрес отписки: %s" % u)
    print("  домен        : %s" % d)
    print("  это prokompressor.ru? %s" % ("ДА — нарушение правила!" if "prokompressor" in d.lower() else "нет"))
except Exception as ex:
    print("  ", str(ex)[:90])
