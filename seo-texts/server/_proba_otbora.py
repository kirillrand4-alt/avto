# -*- coding: utf-8 -*-
"""Проба: одна пачка из 20 событий, смотрим вердикты."""
import importlib.util, io, json, os, sys
sys.path.insert(0, r'C:\sender\server'); os.chdir(r'C:\sender\server')
spec = importlib.util.spec_from_file_location('ot', r'C:\sender\server\otbor_90kvt.py')
ot = importlib.util.module_from_spec(spec); spec.loader.exec_module(ot)
спис = ot.кандидаты()
print('кандидатов:', len(спис))
n = ot.пачка(спис[:20])
print('размечено в пачке:', n)
строки = []
with io.open(ot.ОТЧЁТ, encoding='utf-8', errors='replace') as f:
    for s in f: строки.append(json.loads(s))
print('===ИТОГ===')
print(json.dumps([{'имя': з.get('имя'), 'тип': з.get('тип'), 'a': з.get('a'), 'b': з.get('b'),
                   'что': (з.get('что') or '')[:70], 'ошибка': з.get('ошибка')}
                  for з in строки[-20:]], ensure_ascii=False, indent=1)[:3000])
