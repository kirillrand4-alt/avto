# -*- coding: utf-8 -*-
"""sha256 gen_provider.py на сервере — сверить перед выкаткой (общий каталог)."""
import hashlib
import os

for путь in (r"C:\sender\gen_provider.py", r"C:\sender\sender\ai_quota.py"):
    if not os.path.exists(путь):
        print(f"{путь}: НЕТ")
        continue
    b = open(путь, "rb").read()
    print(f"{путь}: {hashlib.sha256(b).hexdigest()}  {len(b)} байт")
