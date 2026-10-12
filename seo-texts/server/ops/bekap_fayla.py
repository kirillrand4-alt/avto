# -*- coding: utf-8 -*-
"""Копия файла рядом с меткой времени — перед выкаткой поверх."""
import os
import shutil
import sys
import time
п = sys.argv[1]
к = п + ".bak-%d" % int(time.time())
shutil.copy2(п, к)
print("копия: %s (%d байт)" % (os.path.basename(к), os.path.getsize(к)))
print("=== БЭКАП ===")
