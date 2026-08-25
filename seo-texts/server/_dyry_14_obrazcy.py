# -*- coding: utf-8 -*-
"""Образцы текста у пустых паспортов — отличить кракозябры от чужого языка."""
import json

d = json.load(open(r'C:\sender\_tmp\dyra2.json', encoding='utf-8'))
celi = d['celi']
for kl in ('текст почти без кириллицы', 'текст годный, модель вернула пусто',
           'заглушка/ошибка/стройка'):
    gr = [p for p in celi if p.get('klass') == kl]
    gr.sort(key=lambda x: -(x.get('znakov_v_razbore') or 0))
    print('=== %s (%d) ===' % (kl, len(gr)))
    for p in gr[:5]:
        print(' ', p['inn'], '|', (p.get('kesh_site') or '')[:34], '| кир',
              p.get('dolya_kirillicy'), '| зн', p.get('znakov_v_razbore'))
        print('    ', (p.get('obrazec') or '')[:200])
# сколько из пустых можно вернуть переразбором: format<2 или переразборов<2
n_per = sum(1 for p in celi if (p.get('per') or 0) < 2)
print('пустых паспортов с pererazborov<2 (переразбор возможен):', n_per)
print('у скольких popytok>=3 (заперты попытками):', sum(1 for p in celi if (p.get('pop') or 0) >= 3))
