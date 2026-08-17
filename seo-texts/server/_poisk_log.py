# -*- coding: utf-8 -*-
"""Хвост лога поиска сайтов: почему процесс не живёт."""
import io
import os
import sys

sys.stdout.reconfigure(encoding='utf-8')
for p in (r'C:\sender\poisk_saytov.out', r'C:\sender\poisk_saytov.jsonl'):
    if not os.path.exists(p):
        print('--- нет файла:', p)
        continue
    t = io.open(p, encoding='utf-8', errors='replace').read()
    print('--- %s (%d байт) ---' % (p, len(t)))
    print(t[-1800:])
