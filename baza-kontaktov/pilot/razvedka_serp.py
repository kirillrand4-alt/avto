# -*- coding: utf-8 -*-
"""Сборка URL Google/Яндекс в news_scan.col_xmlriver и xmlriver_probe (код, без секретов)."""
import glob, os
p = [x for r in (r'C:\sender\server', r'C:\sender') for x in glob.glob(os.path.join(r, 'news_scan.py'))][0]
t = open(p, encoding='utf-8', errors='replace').read().splitlines()
print('===ИТОГ===')
for a, b in ((481, 560), (1553, 1575)):
    for i in range(a - 1, min(b, len(t))):
        print(i + 1, t[i][:170])
