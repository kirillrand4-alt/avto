# -*- coding: utf-8 -*-
r"""Возраст и происхождение вердиктов с пустым source — на них стоит заслон."""
import json, sqlite3
s = sqlite3.connect('file:C:/sender/sender.db?mode=ro', uri=True)
o = sqlite3.connect('file:C:/sender/obzvon-index.db?mode=ro', uri=True)
обз = {}
for e, v, t in o.execute('select lower(email), verdict, ts from email_probe'):
    обз[e] = (v, str(t or ''))
o.close()
пустые = [(e, v) for e, v in s.execute(
    "select lower(email), verdict from addr_probe where coalesce(source,'')=''")]
свод = {'всего': len(пустые), 'ловушки_catch_all': 0, 'из_обзвона': 0,
        'непонятно_откуда': 0}
по_вердикту = {}
даты = {}
for e, v in пустые:
    по_вердикту[v] = по_вердикту.get(v, 0) + 1
    if e.startswith('nesushchestvuyushchiy-'):
        свод['ловушки_catch_all'] += 1
        continue
    if e in обз:
        свод['из_обзвона'] += 1
        д = обз[e][1][:7]
        даты[д] = даты.get(д, 0) + 1
    else:
        свод['непонятно_откуда'] += 1
# «есть» отдельно: сколько из них старые импортные
есть_обз = sum(1 for e, v in пустые if v == 'есть' and e in обз)
есть_лов = sum(1 for e, v in пустые if v == 'есть'
               and e.startswith('nesushchestvuyushchiy-'))
свод['вердиктов_есть_всего'] = по_вердикту.get('есть', 0)
свод['из_них_импорт_из_обзвона'] = есть_обз
свод['из_них_ловушки_catch_all'] = есть_лов
свод['по_вердикту'] = по_вердикту
свод['когда_проверял_обзвон'] = dict(sorted(даты.items()))
s.close()
print(json.dumps(свод, ensure_ascii=False, indent=1))
