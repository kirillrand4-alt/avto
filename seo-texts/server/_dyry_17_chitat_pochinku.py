# -*- coding: utf-8 -*-
"""Прочитать результат замера починки дыры 1."""
import json
import os
import re
import time

p = r'C:\sender\_tmp\dyra1_pochinka.json'
if not os.path.exists(p):
    print('файла ещё нет — прогон не закончился')
    raise SystemExit(0)
print('файл от', time.strftime('%m-%d %H:%M', time.localtime(os.path.getmtime(p))))
d = json.load(open(p, encoding='utf-8'))
dok, nd = d['dokazan'], d['ne_dokazan']
print('паспортов в день:', json.dumps(d['tempo'], ensure_ascii=False))
print('ДОКАЗАНА привязка (ИНН/ОГРН на своей странице):', len(dok),
      '| из них >=9 страниц:', sum(1 for r in dok if r['devyat']))
print('НЕ доказана:', len(nd), '| из них >=9 страниц:', sum(1 for r in nd if r['devyat']))
print('кэш не прочитался:', d['bez_fajla'])
dm = {}
for r in dok:
    x = re.sub(r'^https?://(www\.)?', '', r['kesh_site']).split('/')[0]
    dm[x] = dm.get(x, 0) + 1
print('топ доменов доказанных:', json.dumps(
    dict(sorted(dm.items(), key=lambda x: -x[1])[:10]), ensure_ascii=False)[:500])
ist = {}
for r in dok:
    ist[r['istochnik']] = ist.get(r['istochnik'], 0) + 1
print('источник кэша у доказанных:', json.dumps(ist, ensure_ascii=False))
print('30 ПРИМЕРОВ ДОКАЗАННЫХ:')
for r in sorted(dok, key=lambda x: -x['stranic'])[:30]:
    print(' ', r['inn'], '|стр', r['stranic'], '|', r['kesh_site'][:40], '|', r['name'][:32])
