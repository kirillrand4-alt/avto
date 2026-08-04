# -*- coding: utf-8 -*-
"""155 фактов, которые моя разметка пропускает: смотрю ПОЧЕМУ, прежде чем чинить правило.

Находка 2-й сессии: метка equipment_type «центробежная» стоит вместе с явным признаком чужой
машины (вентилятор, дымосос, поршневой, Рутс, АВО, насос). Таких 164, из них 155 моя разметка
НЕ сворачивает. Моя гипотеза была «правило ломается на перечислениях». Гипотезу надо
проверить, а не чинить по ней: печатаю сами цитаты и то, каким видом их пометило правило.
"""
import collections
import importlib.util
import json
import re
import sqlite3

spec = importlib.util.spec_from_file_location('mf', r'C:\sender\_ops\3s_musor_faktov.py')
mf = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mf)

sale = sqlite3.connect(r'C:\seostat\data\centro_sales.db')
sale.execute('attach database ? as f', (r'C:\seostat\data\centrifugal.db',))
svernuto = {r[0] for r in sale.execute("select value from hidden_item where kind='fact'")}
CHUZHOE = re.compile(r'вентилятор|дымосос|поршнев|винтов|Рутс|\bАВО\b|\bнасос', re.I)

sch = collections.Counter()
primery = collections.defaultdict(list)
for fid, tip, quote in sale.execute(
        "select id, coalesce(equipment_type,''), coalesce(quote,'') from f.fact"):
    if 'центробежн' not in tip.lower() or not CHUZHOE.search(quote):
        continue
    if str(fid) in svernuto:
        sch['уже свёрнуто'] += 1
        continue
    vid, pochemu = mf.razobrat(quote, tip)
    sch[vid] += 1
    if len(primery[vid]) < 4:
        primery[vid].append({'citata': quote[:150], 'pochemu': pochemu[:110]})
print(json.dumps({'по_видам': dict(sch), 'примеры': dict(primery)}, ensure_ascii=False, indent=1))
