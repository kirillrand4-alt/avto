# -*- coding: utf-8 -*-
r"""Замер: что реально даёт перебор выдачи вниз вместо остановки на первом.

Берём компании, которые прошлый прогон списал на площадке, и прогоняем их
НОВОЙ логикой целиком — с открытием страниц и вердиктом. Считаем, скольким
это дало подтверждённый сайт, скольким кандидата, а скольким ничего.

    python _zamer_perebora.py [сколько]
"""
import json
import os
import sqlite3
import sys

DIR = r'C:\sender\server'
sys.path.insert(0, DIR)
os.chdir(DIR)
import poisk_saytov as PS  # noqa: E402

СКОЛЬКО = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else 60

лог = r'C:\sender\poisk_saytov.jsonl'
жертвы, видели = [], set()
with open(лог, encoding='utf-8', errors='replace') as f:
    for s in f:
        try:
            d = json.loads(s)
        except Exception:  # noqa: BLE001
            continue
        if d.get('site'):
            continue
        src = str(d.get('src') or '')
        if not (src.startswith('площадка') or src.startswith('справочник')):
            continue
        i = d.get('inn')
        if i and i not in видели:
            видели.add(i)
            жертвы.append((i, src[:34]))
        if len(жертвы) >= СКОЛЬКО:
            break

o = sqlite3.connect(r'C:\sender\obzvon-index.db')
задачи, прежнее = [], {}
for инн, src in жертвы:
    r = o.execute("select coalesce(name_short,name_full,''), coalesce(region,'') "
                  'from obzvon where inn=?', (инн,)).fetchone()
    if r:
        задачи.append({'inn': инн, 'name': r[0], 'city': r[1], 'revenue': 0})
        прежнее[инн] = src
o.close()

# прогон НЕ через PS.прогон (тот пишет в базу и лог) — только функция «одна»
import enrich_contacts as EC  # noqa: E402,F401  (нужен внутри одна())
from concurrent.futures import ThreadPoolExecutor  # noqa: E402

# собираем ту же «одна», что стоит в прогоне: вызываем прогон на пустом наборе
# нельзя, поэтому повторяем вызов через сам модуль
import types  # noqa: E402,F401

свод = {'взято': len(задачи), 'подтверждён': 0, 'кандидат': 0, 'по_прежнему_нет': 0}
находки = []


def одна(k):
    спис, src, card = EC.kandidaty_sayta(k)
    итог = {'инн': k['inn'], 'имя': k['name'][:36], 'было': прежнее.get(k['inn'], ''),
            'кандидатов': len(спис)}
    открыт = закрыт = None
    отказы = []
    сл = PS._slova(k['name'])
    import ploshchadki as PL
    import re as _re
    for site, ист in спис:
        п = PL.из_списка(site)
        if п:
            отказы.append('площадка:' + п)
            continue
        try:
            html, _s, _m = EC._fetch_site(site)
        except Exception:  # noqa: BLE001
            html = ''
        if not html:
            закрыт = закрыт or site
            отказы.append('не открылся:' + PL.домен(site))
            continue
        h = html.upper()
        имя_на = bool(сл and sum(1 for w in сл if w in h) >= max(1, len(сл) // 2))
        свой = имя_на or PL.домен(site).split('.')[0] in PS._translit_imeni(k['name'])
        отк = PL.площадка(site, html, k['inn'], свой_домен_или_имя=свой)
        if отк:
            отказы.append(отк[:30])
            continue
        if k['inn'] in _re.sub(r'\D', '', html):
            итог.update({'стало': site, 'вердикт': 'инн-на-сайте', 'отсеяно': отказы[:3]})
            return итог
        if имя_на:
            итог.update({'стало': site, 'вердикт': 'имя-на-сайте', 'отсеяно': отказы[:3]})
            return итог
        открыт = открыт or site
    зап = открыт or закрыт
    итог.update({'стало': зап, 'вердикт': '' if зап else 'нет', 'отсеяно': отказы[:3]})
    return итог


with ThreadPoolExecutor(max_workers=6) as ex:
    for r in ex.map(одна, задачи):
        if r.get('вердикт') in ('инн-на-сайте', 'имя-на-сайте'):
            свод['подтверждён'] += 1
            находки.append(r)
        elif r.get('стало'):
            свод['кандидат'] += 1
            находки.append(r)
        else:
            свод['по_прежнему_нет'] += 1

print(json.dumps({'свод': свод, 'находки': находки[:14]}, ensure_ascii=False, indent=1))
