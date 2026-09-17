# -*- coding: utf-8 -*-
"""Проба на трёх событиях: есть ли кандидаты и качается ли текст."""
import json, os, sys
sys.path.insert(0, r'C:\sender\server'); os.chdir(r'C:\sender\server')
sys.argv = ['x', '3']
import importlib.util
spec = importlib.util.spec_from_file_location('dt', r'C:\sender\server\dobor_teksta.py')
dt = importlib.util.module_from_spec(spec); spec.loader.exec_module(dt)
спис = dt.кандидаты(3)
print('кандидатов найдено:', len(спис))
for d in спис:
    print(' ', str(d.get('company'))[:30], '|', (d.get('source_url') or '')[:70])
if спис:
    з = dt.обработать(спис[0])
    print('===ИТОГ===')
    print(json.dumps(з, ensure_ascii=False, indent=1)[:1500])
