# -*- coding: utf-8 -*-
"""Финал: promrnd в цифрах + чистая таблица 30 примеров с ИНН."""
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


cx = sqlite3.connect('file:C:/sender/enrich.db?mode=ro', uri=True, timeout=30)
O = {}
pr = грузи(r'C:\sender\_tmp\promrnd_cards.jsonl')
ok = [x for x in pr if x.get('st') == 200]
инны = [x['inn'] for x in ok if x.get('inn')]
наши = {}
for i in range(0, len(инны), 400):
    part = инны[i:i + 400]
    for r in cx.execute("SELECT inn, name, region, COALESCE(revenue_rub,0), COALESCE(site,''), "
                        "COALESCE(cand_site,'') FROM companies WHERE inn IN (%s)"
                        % ','.join('?' * len(part)), part):
        наши[r[0]] = r
нах = [x for x in ok if наши.get(x.get('inn')) and not наши[x['inn']][4]
       and not наши[x['inn']][5] and x.get('ext')]
дом = {}
for x in ok:
    for hh in (x.get('ext') or [])[:1]:
        дом.setdefault(hh, []).append(x['inn'])
O['promrnd'] = {
    'проб_id': len(pr), 'карточек_200': len(ok), 'с_ИНН': len(инны),
    'уникальных_ИНН': len(set(инны)), 'с_ОГРН': sum(1 for x in ok if x.get('ogrn')),
    'с_внешним_сайтом': sum(1 for x in ok if x.get('ext')),
    'с_почтой': sum(1 for x in ok if x.get('email')),
    'с_датой_регистрации_карточки': sum(1 for x in ok if x.get('на_портале_с')),
    'наших_по_ИНН': len(наши), 'НЕ_наших': len(set(инны)) - len(наши),
    'наших_без_сайта': sum(1 for r in наши.values() if not r[4] and not r[5]),
    'находок': len(нах),
    'доменов_на_2+_компании': sorted(((len(v), k) for k, v in дом.items() if len(v) > 1),
                                     reverse=True)[:6],
    'примеры_находок': [[x['inn'], (наши[x['inn']][1] or '')[:30],
                         int(наши[x['inn']][3] or 0) // 1000000, x['ext'][0]] for x in нах[:8]],
    'max_id_живой': max([x['id'] for x in ok] or [0])}
# чистая таблица 30 примеров
d = грузи(r'C:\sender\_tmp\spr_dokaz.jsonl')
d.sort(key=lambda x: (-(2 if x['улика'] == 'ИНН' else 1 if x['улика'] == 'имя' else 0),
                      -(x['rev'] or 0)))
таб = []
for x in d[:30]:
    таб.append([x['inn'], (x['name'] or '')[:38], round((x['rev'] or 0) / 1e6, 1),
                x['домен'], x['источник'][:20], x['улика']])
O['таблица30'] = таб
cx.close()
with open(r'C:\sender\_tmp\spr_final.json', 'w', encoding='utf-8') as f:
    json.dump(O, f, ensure_ascii=False, indent=1)
    f.flush()
    os.fsync(f.fileno())
print(json.dumps(O, ensure_ascii=False)[:5800])
