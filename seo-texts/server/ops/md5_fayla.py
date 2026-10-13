# -*- coding: utf-8 -*-
"""md5 файлов на сервере (сверка перед перезаписью): md5_fayla.py <путь> [...]"""
import hashlib
import sys
for п in sys.argv[1:]:
    try:
        print("%s %s" % (hashlib.md5(open(п, "rb").read()).hexdigest(), п))
    except Exception as е:  # noqa: BLE001
        print("нет: %s (%s)" % (п, е))
print("=== MD5 ===")
