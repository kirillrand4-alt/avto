# -*- coding: utf-8 -*-
"""Только чтение: confirm_* методы и как боевой код пишет extra по ключу."""
import inspect
import sys

sys.path.insert(0, r"C:\sender")
from sender.config import Config    # noqa: E402
from sender.store import Store      # noqa: E402
from sender import ai_quota         # noqa: E402

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))

print("=== как ai_quota пишет extra по ключу (образец для группы) ===")
try:
    src = inspect.getsource(ai_quota)
    import re
    for m in re.finditer(r"def (_?[a-zA-Zа-яА-Я_]*extra[a-zA-Zа-яА-Я_]*)\(", src):
        print("  функция:", m.group(1))
    i = src.find("_perestavit_napravlenie")
    if i > 0:
        j = src.find("def ", i)
        print("\n  --- _perestavit_napravlenie ---")
        for x in src[j:j + 1500].splitlines()[:34]:
            print("   " + x[:120])
except Exception as ex:
    print("  не достал:", str(ex)[:100])

print("\n=== ИТОГ: ВСЕ confirm_* методы Store ===")
for имя in sorted(dir(store)):
    if имя.startswith("confirm"):
        f = getattr(store, имя)
        if callable(f):
            print("  %-24s %s" % (имя, str(inspect.signature(f))[:150]))
