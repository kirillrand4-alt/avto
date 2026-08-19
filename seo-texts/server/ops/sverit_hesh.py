# -*- coding: utf-8 -*-
"""sha256 файлов пакета sender на сервере — сверить ПЕРЕД выкаткой.

C:\\sender\\sender\\ общий с соседней сессией: молча перезаписать её правку
нельзя. Сверяем хеш до, а не после.
"""
import hashlib
import os
import sys

БАЗА = r"C:\sender\sender"
for имя in sys.argv[1:]:
    путь = os.path.join(БАЗА, имя.replace("/", os.sep))
    if not os.path.exists(путь):
        print(f"{имя}: НЕТ НА СЕРВЕРЕ")
        continue
    b = open(путь, "rb").read()
    print(f"{имя}: {hashlib.sha256(b).hexdigest()}  {len(b)} байт  "
          f"изменён {os.path.getmtime(путь):.0f}")
