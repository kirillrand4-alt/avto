# -*- coding: utf-8 -*-
"""Свод 2: АПК-раздел agrobase против нашей базы (гипотеза владельца о новых
компаниях) + прогресс agro."""
import io
import json
import os
import sqlite3
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
O = {}
cx = sqlite3.connect('file:C:/sender/enrich.db?mode=ro', uri=True, timeout=30)


def грузи(p):
    r = []
    if os.path.exists(p):
        for ln in io.open(p, encoding='utf-8', errors='replace'):
            try:
                r.append(json.loads(ln))
            except Exception:
                pass
    return r


def сверь(recs, метка):
    инны = [x['inn'] for x in recs if x.get('inn')]
    наши = {}
    for i in range(0, len(инны), 400):
        part = инны[i:i + 400]
        q = ("SELECT inn, substr(name,1,36), region, COALESCE(revenue_rub,0), "
             "COALESCE(site,''), COALESCE(cand_site,'') FROM companies WHERE inn IN (%s)"
             % ','.join('?' * len(part)))
        for r in cx.execute(q, part):
            наши[r[0]] = r
    d = {'карточек': len(recs), 'с_инн': len(инны), 'наших': len(наши),
         'не_наших': len(set(инны)) - len(наши),
         'наших_без_сайта': sum(1 for r in наши.values() if not r[4] and not r[5])}
    O[метка] = d
    return наши


апк = грузи(r'C:\sender\_tmp\agro_apk_sample.jsonl')
сверь(апк, 'apk_выборка400')
аг = грузи(r'C:\sender\_tmp\agro_cards.jsonl')
наши_аг = сверь(аг, 'agro_производители')
O['agro_с_внешним_сайтом'] = sum(1 for x in аг if x.get('ext'))
нах = []
for x in аг:
    r = наши_аг.get(x.get('inn'))
    if r and not r[4] and not r[5] and x.get('ext'):
        нах.append([r[0], r[1], int(r[3] or 0), x['ext'][0]])
нах.sort(key=lambda a: -a[2])
O['agro_находок_для_безсайтовых'] = len(нах)
O['agro_топ_находок'] = нах[:8]
# домены на много компаний
дом = {}
for x in аг:
    for h in (x.get('ext') or [])[:1]:
        дом.setdefault(h, []).append(x.get('inn'))
O['agro_доменов'] = len(дом)
O['agro_домен_много'] = sorted(((len(v), k) for k, v in дом.items() if len(v) > 1),
                               reverse=True)[:10]
cx.close()
for f in ('spr_ozav.log', 'spr_agro.log'):
    try:
        O.setdefault('логи', {})[f] = open(r'C:\sender\_tmp\%s' % f,
                                           encoding='utf-8', errors='replace').read()[-100:]
    except Exception as e:
        O.setdefault('логи', {})[f] = str(e)[:40]
print(json.dumps(O, ensure_ascii=False)[:5700])
