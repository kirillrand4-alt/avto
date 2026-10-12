# -*- coding: utf-8 -*-
"""Хэш и размер файла на сервере — сверка с репо перед выкаткой."""
import hashlib
import os
import sys
import time
п = sys.argv[1]
д = open(п, "rb").read()
print("%s  %d байт  %s  изменён %s" % (hashlib.sha256(д).hexdigest()[:16], len(д),
      os.path.basename(п), time.strftime("%Y-%m-%d %H:%M",
                                         time.localtime(os.path.getmtime(п)))))
print("=== ХЭШ ===")
