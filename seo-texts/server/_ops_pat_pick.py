# -*- coding: utf-8 -*-
"""Разведка №0: отобрать компании под два непроверенных источника.

Источник A — ПАТЕНТЫ: нужен машиностроительный/производственный профиль.
Источник B — РАСКРЫТИЕ АО: нужны только АО/ПАО (ООО ничего не публикует).

Ничего не пишем, только печатаем список кандидатов.
"""
import json
import re
import sys

sys.path.insert(0, r'C:\sender\server')
sys.path.insert(0, r'C:\sender\_ops')
import enrich_db as EDB          # noqa: E402
import enrich_contacts as EC     # noqa: E402

db = EDB.EnrichDB()
e = db.cx

БАЗА = json.load(open(r'C:\sender\_ops\sales_base.json', encoding='utf-8'))
инны = []
было = set()
for строки in БАЗА.values():
    for x in строки:
        i = str(x.get('inn') or '').strip()
        if i and i not in было:
            было.add(i)
            инны.append((i, str(x.get('name') or '')))

print('всего ИНН в sales_base:', len(инны))

_АО = re.compile(r'(^|[^а-яё])(АО|ПАО|ОАО|ЗАО|АКЦИОНЕРНОЕ\s+ОБЩЕСТВО|'
                 r'ПУБЛИЧНОЕ\s+АКЦИОНЕРНОЕ|ОТКРЫТОЕ\s+АКЦИОНЕРНОЕ|'
                 r'ЗАКРЫТОЕ\s+АКЦИОНЕРНОЕ)([^а-яё]|$)', re.I)

ао, прочие = [], []
for i, n in инны:
    r = e.execute('SELECT name, site, okved, is_competitor FROM companies '
                  'WHERE inn=?', (i,)).fetchone()
    имя = (r[0] if r and r[0] else n) or ''
    сайт = (r[1] if r else '') or ''
    оквэд = (r[2] if r else '') or ''
    конк = (r[3] if r else 0) or 0
    бренд = EC.бренд_компании(имя, сайт)
    зап = {'inn': i, 'name': имя[:70], 'brand': бренд, 'site': сайт[:40],
           'okved': оквэд, 'competitor': конк}
    if _АО.search(имя):
        ао.append(зап)
    else:
        прочие.append(зап)

print('АО/ПАО/ОАО/ЗАО:', len(ао), ' прочих:', len(прочие))
print('--- АО (первые 40) ---')
for x in ао[:40]:
    print(json.dumps(x, ensure_ascii=False))
print('--- прочие (первые 30) ---')
for x in прочие[:30]:
    print(json.dumps(x, ensure_ascii=False))
print('ИТОГ ao=%d prochih=%d vsego=%d' % (len(ао), len(прочие), len(инны)))
