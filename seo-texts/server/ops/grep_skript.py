# -*- coding: utf-8 -*-
"""Найти, где лежит скрипт по имени, и показать его строки с моделями/шапку
(без строк с token/key/password): grep_skript.py <имя.py>..."""
import glob
import io
import re
import sys
for имя in sys.argv[1:]:
    for п in glob.glob(r"C:\**\%s" % имя, recursive=True)[:2]:
        print("=====", п)
        т = io.open(п, encoding="utf-8", errors="replace").read().splitlines()
        print("\n".join(т[:12]))
        for i, s in enumerate(т):
            if re.search(r"(?i)claude-|model|effort|thinking|environ.get", s) and not re.search(r"(?i)api_key|passw|DROP_TOKEN", s):
                print("  %d: %s" % (i + 1, s.strip()[:160]))
