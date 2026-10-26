# -*- coding: utf-8 -*-
"""grep по *.py в каталоге (рекурсивно, без bak/ops): grep_dir.py <каталог> <регулярка>. Только чтение."""
import io
import os
import re
import sys
рег = re.compile(sys.argv[2])
for кор, папки, файлы in os.walk(sys.argv[1]):
    папки[:] = [п for п in папки if п not in ("ops", "__pycache__", "node_modules", ".venv", "tests")]
    for ф in файлы:
        if not ф.endswith(".py"):
            continue
        п = os.path.join(кор, ф)
        try:
            for i, s in enumerate(io.open(п, encoding="utf-8", errors="replace"), 1):
                if рег.search(s):
                    print("%s:%d: %s" % (п, i, s.rstrip()[:160]))
        except OSError:
            pass
