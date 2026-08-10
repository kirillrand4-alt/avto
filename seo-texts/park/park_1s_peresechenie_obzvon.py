# -*- coding: utf-8 -*-
"""Сколько предприятий парка УЖЕ видны в базе обзвона «Центробежные».

Считаем ровно то множество, которое продавец ВИДИТ: назначено пользователю, есть в
исходной базе центробежных и не скрыто. Именно про него владелец сказал «есть в базе
центробежных и отображаются».
"""
import json, sqlite3

S = r'C:\seostat\data\centro_sales.db'
C = r'C:\seostat\data\centrifugal.db'
s = sqlite3.connect('file:%s?mode=ro' % S, uri=True)
c = sqlite3.connect('file:%s?mode=ro' % C, uri=True)
naz = {r[0] for r in s.execute("select inn from company_assignment")}
skryt = {r[0] for r in s.execute("select inn from hidden_item where kind='company'")}
est = {r[0] for r in c.execute("select inn from company")}
vidno = (naz & est) - skryt
o = {'назначено': len(naz), 'в базе центробежных': len(est), 'скрыто': len(skryt),
     'ОТОБРАЖАЕТСЯ ОПЕРАТОРУ': len(vidno)}
open(r'C:\sender\_obzvon_vidno.json', 'w', encoding='utf-8').write(
    json.dumps(sorted(vidno), ensure_ascii=False))
o['файл'] = r'C:\sender\_obzvon_vidno.json'
print(json.dumps(o, ensure_ascii=False, indent=1))
