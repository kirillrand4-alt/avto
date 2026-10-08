# -*- coding: utf-8 -*-
"""Исправитель A2: убрать СВОИ временные копии базы продаж (fixA2-test-*.db, fixA2-render-*.db,
fixA2-razv-*.db) и копию шаблонов сухого прогона из C:\\centro2\\_bekap. Бэкапы файлов
(fixA2-ГГГГММДД-…, fixA2-doc-…) остаются."""
import os
import re
import shutil

B = r'C:\centro2\_bekap'
for f in sorted(os.listdir(B)):
    p = os.path.join(B, f)
    if re.match(r'fixA2-(?:test|render|razv)-\d+\.db$', f):
        try:
            os.remove(p)
            print('удалено:', f)
        except OSError as e:
            print('не удалено:', f, e)
    elif f == 'fixA2-stage':
        shutil.rmtree(p, ignore_errors=True)
        print('удалено:', f)
print('осталось A2:', sorted(x for x in os.listdir(B) if x.startswith('fixA2')))
