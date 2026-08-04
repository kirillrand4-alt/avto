# -*- coding: utf-8 -*-
"""Проба перед прогоном: есть ли на сервере tp_raw.json, доступен ли дроп, наши ли это ИНН.

Три вопроса, на которые дешевле ответить одним заданием, чем узнать их ответы по
провалу большого прогона.
"""
import glob
import json
import os
import sqlite3

est = [p for p in glob.glob(r'C:\sender\_ops\tp*.json')]
print('файлы tp*: %s' % [(os.path.basename(p), os.path.getsize(p) // 1024) for p in est])
print('DROP_URL задан: %s, DROP_TOKEN задан: %s'
      % (bool(os.environ.get('DROP_URL')), bool(os.environ.get('DROP_TOKEN'))))

b = sqlite3.connect('file:C:/seostat/data/p25.db?mode=ro', uri=True)
nashi = {i for (i,) in b.execute('select inn from company')}
print('ИНН в p25.company: %d' % len(nashi))

put = next((p for p in est if 'raw' in p), '')
if put:
    d = json.load(open(put, encoding='utf-8'))
    kart = d.get('карточки') or []
    inn_kart = {k['inn'] for k in kart}
    print('карточек %d, предприятий в них %d' % (len(kart), len(inn_kart)))
    print('ИТОГ ' + json.dumps({
        'предприятий с карточками': len(inn_kart),
        'из них НАШИ покупатели P25': len(inn_kart & nashi),
        'не наши': len(inn_kart - nashi)}, ensure_ascii=False))
else:
    print('ИТОГ ' + json.dumps({'tp_raw.json': 'на сервере нет'}, ensure_ascii=False))
