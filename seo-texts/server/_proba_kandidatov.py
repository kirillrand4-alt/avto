# -*- coding: utf-8 -*-
r"""Проба разбора выдачи: сколько кандидатов даёт один запрос и что отсеивается.

Берём несколько компаний, которые прошлый прогон списал в «площадка», и
смотрим, что стоит НИЖЕ отброшенного адреса в той же самой выдаче.
"""
import json
import os
import sys

DIR = r'C:\sender\server'
sys.path.insert(0, DIR)
os.chdir(DIR)
import poisk_saytov as PS      # noqa: E402  (он же поднимает ключи)
import enrich_contacts as EC   # noqa: E402
import ploshchadki as PL       # noqa: E402

лог = r'C:\sender\poisk_saytov.jsonl'
жертвы, видели = [], set()
if os.path.exists(лог):
    with open(лог, encoding='utf-8', errors='replace') as f:
        for s in f:
            try:
                d = json.loads(s)
            except Exception:  # noqa: BLE001
                continue
            if d.get('site') or not str(d.get('src', '')).startswith('площадка'):
                continue
            i = d.get('inn')
            if i and i not in видели:
                видели.add(i)
                жертвы.append((i, d.get('src')))
            if len(жертвы) >= 6:
                break

import sqlite3  # noqa: E402
o = sqlite3.connect(r'C:\sender\obzvon-index.db')
вышло = []
for инн, прежний in жертвы:
    r = o.execute("select coalesce(name_short,name_full,''), coalesce(region,'') "
                  'from obzvon where inn=?', (инн,)).fetchone()
    if not r:
        continue
    k = {'inn': инн, 'name': r[0], 'city': r[1]}
    спис, ист, card = EC.kandidaty_sayta(k)
    вышло.append({
        'инн': инн, 'имя': r[0][:40], 'прежний_вердикт': прежний,
        'карточка_сайт': card.get('website', ''),
        'кандидатов': len(спис),
        'очередь': [{'адрес': s, 'источник': и,
                     'площадка': PL.из_списка(s) or ''} for s, и in спис],
    })
o.close()
print(json.dumps(вышло, ensure_ascii=False, indent=1))
