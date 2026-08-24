# -*- coding: utf-8 -*-
"""Совпадает ли боевой файл с моим репозиторным до правки (md5)."""
import hashlib
import io
import os

for имя in ("addr_probe.py", "store.py", "leaddesk.py", "imap_watcher.py"):
    путь = os.path.join(r"C:\sender\sender", имя)
    try:
        b = io.open(путь, "rb").read()
        print("%-18s md5=%s  %d байт" % (имя, hashlib.md5(b).hexdigest()[:12], len(b)))
    except Exception as e:  # noqa: BLE001
        print("%-18s НЕ ПРОЧИТАН: %s" % (имя, e))
