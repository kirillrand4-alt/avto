# -*- coding: utf-8 -*-
"""Сколько НОВЫХ юрлиц (нет в наших 166 620) дают источники вместе, с сайтом и без."""
import io
import json
import os
import re
import sqlite3
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')


def грузи(p):
    r = []
    if os.path.exists(p):
        for ln in io.open(p, encoding='utf-8', errors='replace'):
            try:
                r.append(json.loads(ln))
            except Exception:
                pass
    return r


ист = {}
for x in грузи(r'C:\sender\_tmp\ozav_cards.jsonl'):
    if x.get('inn'):
        ист.setdefault(x['inn'], set()).add(('o-zavodah', bool(x.get('site'))))
for x in грузи(r'C:\sender\_tmp\agro_cards.jsonl'):
    if x.get('inn'):
        ист.setdefault(x['inn'], set()).add(('agrobase-произв', bool(x.get('ext'))))
for x in грузи(r'C:\sender\_tmp\agro_apk_sample.jsonl'):
    if x.get('inn'):
        ист.setdefault(x['inn'], set()).add(('agrobase-АПК', False))
for x in грузи(r'C:\sender\_tmp\promrnd_sites.jsonl'):
    if x.get('inn'):
        ист.setdefault(x['inn'], set()).add(('promrnd', bool(x.get('site'))))
инны = list(ист)
cx = sqlite3.connect('file:C:/sender/enrich.db?mode=ro', uri=True, timeout=30)
есть = set()
for i in range(0, len(инны), 400):
    part = инны[i:i + 400]
    for r in cx.execute("SELECT inn FROM companies WHERE inn IN (%s)"
                        % ','.join('?' * len(part)), part):
        есть.add(r[0])
cx.close()
новые = [i for i in инны if i not in есть]
новые_с_сайтом = [i for i in новые if any(s for _n, s in ист[i])]
по_ист = {}
for i in новые:
    for n, s in ист[i]:
        d = по_ист.setdefault(n, {'новых': 0, 'из_них_с_сайтом': 0})
        d['новых'] += 1
        d['из_них_с_сайтом'] += bool(s)
пересеч = sum(1 for i in инны if len({n for n, _s in ист[i]}) > 1)
print(json.dumps({
    'уникальных_ИНН_во_всех_каталогах': len(инны),
    'из_них_уже_в_нашей_базе': len(есть),
    'НОВЫХ_для_нас': len(новые),
    'новых_с_сайтом_на_карточке': len(новые_с_сайтом),
    'по_источникам': по_ист,
    'ИНН_встретился_в_2+_каталогах': пересеч,
}, ensure_ascii=False)[:3000])
