# -*- coding: utf-8 -*-
"""Флаг сметной проверки — через собственный запросчик коллектора (его формат рабочий)."""
import json
import sys

sys.path.insert(0, r'C:\sender\server')
import collector_egrz as C  # noqa: E402

o = {}
ДАТА = '2026-06-19T00:00:00Z'
ОСН = ("ExpertiseConclusionDate gt %s and "
       "ExpertiseResultType eq 'Положительное заключение'" % ДАТА)

for имя, флт in (
        ('всего_положительных', ОСН),
        ('со_сметной_проверкой', ОСН + ' and ExamTypeCost eq true'),
        ('без_сметной_проверки', ОСН + ' and ExamTypeCost eq false')):
    try:
        код, d = C._page(флт, 0, top=1)
        o[имя + '_код'] = код
        o[имя] = d.get('@odata.count')
        if имя == 'со_сметной_проверкой' and d.get('value'):
            зап = d['value'][0]
            o['поля_записи'] = sorted(зап.keys())
            o['образец'] = {k: str(зап.get(k))[:70] for k in list(зап.keys())[:16]}
    except Exception as e:
        o[имя] = 'ОШИБКА: %r' % (e,)

print('===ИТОГ===')
print(json.dumps(o, ensure_ascii=False, indent=1))
