# -*- coding: utf-8 -*-
r"""Проверка направления глазами: сходится ли division обзвона с доменом ящика.

Владелец 20.08: «только проверяй глазами, там ошибки были сначала». Поэтому
смотрим не только итог, но и РАСХОЖДЕНИЯ: письмо ушло с мейеровского домена, а
компания в обзвоне помечена «kc», и наоборот. Каждое такое расхождение — либо
ошибка в division, либо письмо ушло не тем направлением.
"""
import json
import sys

sys.path.insert(0, r'C:\sender')
from sender.store import Store  # noqa: E402

МЕЙЕР = ('optic-sort.ru', 'sort-systems.ru', 'zernosort.ru',
         'usort.ru', 'vsefotoseparatory.ru', 'meyer-corp.ru')
s = Store(r'C:\sender\sender.db')
итог = {}

# 1. итог по направлениям
всё = s.otpravlennye(limit=500)
свод = {}
for p in всё['pisma']:
    свод[p.get('napravlenie') or '(пусто)'] = \
        свод.get(p.get('napravlenie') or '(пусто)', 0) + 1
итог['последние_500_по_направлению'] = свод
итог['всего_писем'] = всё['vsego']

# 2. работает ли фильтр
for н in ('kc', 'meyer'):
    r = s.otpravlennye(napravlenie=н, limit=3)
    итог['фильтр_' + н] = {
        'всего': r['vsego'],
        'примеры': [{'кому': x['email'], 'компания': (x.get('company_name') or '')[:28],
                     'с_ящика': x.get('mailbox_id'), 'напр': x.get('napravlenie')}
                    for x in r['pisma']]}

# 3. РАСХОЖДЕНИЯ: домен ящика против вердикта
расх = []
for p in всё['pisma']:
    ящик = str(p.get('mailbox_id') or '').lower()
    по_домену = 'meyer' if any(ящик.endswith('@' + d) for d in МЕЙЕР) else 'kc'
    if p.get('napravlenie') != по_домену:
        расх.append({'кому': p['email'], 'инн': p.get('inn'),
                     'компания': (p.get('company_name') or '')[:30],
                     'с_ящика': ящик, 'по_домену': по_домену,
                     'итог': p.get('napravlenie')})
итог['расхождений_из_500'] = len(расх)
итог['примеры_расхождений'] = расх[:10]
print(json.dumps(итог, ensure_ascii=False, indent=1)[:3000])
