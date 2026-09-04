# -*- coding: utf-8 -*-
"""Этап 0б: индексы по ключевым фразам из выгрузки обеих ПС.

Вход: _sq.csv (дроп, search_query_2026-06-13_2026-07-12.csv) - колонки
Источник;Сайт;URL;Запрос;Клики;Показы;CTR %;Позиция

Выход:
  keys-by-url.json   URL -> {яндекс:[...], google:[...], итоги}
  cannibals.json     URL -> список пересечений с другими нашими URL по запросу
"""
import csv, json, os, collections

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, '_sq.csv')
SITE = 'https://prokompressor.ru/'
csv.field_size_limit(10 ** 8)

rows = []
with open(SRC, encoding='utf-8-sig') as f:
    r = csv.reader(f, delimiter=';')
    next(r)
    for x in r:
        if len(x) >= 8 and x[1] == SITE:
            rows.append((x[0], x[2], x[3], int(x[4] or 0), int(x[5] or 0), float(x[7] or 0)))

by_url = collections.defaultdict(lambda: {'Яндекс': [], 'Google': []})
by_query = collections.defaultdict(lambda: collections.defaultdict(list))
for src, url, q, cl, sh, pos in rows:
    if src not in ('Яндекс', 'Google'):
        continue
    by_url[url][src].append({'q': q, 'clicks': cl, 'shows': sh, 'pos': pos})
    by_query[q][src].append((url, cl, sh, pos))

out = {}
for url, d in by_url.items():
    rec = {}
    for eng in ('Яндекс', 'Google'):
        e = sorted(d[eng], key=lambda x: -x['shows'])
        sh = sum(x['shows'] for x in e)
        cl = sum(x['clicks'] for x in e)
        rec[eng] = {
            'queries': len(e), 'shows': sh, 'clicks': cl,
            'ctr': round(100 * cl / sh, 2) if sh else 0.0,
            'wpos': round(sum(x['pos'] * x['shows'] for x in e) / sh, 1) if sh else 0.0,
            'top': e[:30],
        }
    rec['shows_total'] = rec['Яндекс']['shows'] + rec['Google']['shows']
    rec['clicks_total'] = rec['Яндекс']['clicks'] + rec['Google']['clicks']
    # запросов в зоне роста 11-30
    z = [x for eng in ('Яндекс', 'Google') for x in d[eng] if 10 < x['pos'] <= 30]
    rec['zone_11_30_queries'] = len(z)
    rec['zone_11_30_shows'] = sum(x['shows'] for x in z)
    out[url] = rec

json.dump(out, open(os.path.join(HERE, 'keys-by-url.json'), 'w'), ensure_ascii=False)
print('keys-by-url.json:', len(out), 'URL')

# каннибализация: запрос, где у нас 2+ URL с показами в одной ПС
cann = collections.defaultdict(list)
for q, per in by_query.items():
    for eng, lst in per.items():
        if len(lst) < 2:
            continue
        lst = sorted(lst, key=lambda x: -x[2])
        for url, cl, sh, pos in lst:
            if sh < 5:
                continue
            rivals = [{'url': u2, 'shows': s2, 'pos': p2}
                      for u2, c2, s2, p2 in lst if u2 != url][:5]
            if rivals:
                cann[url].append({'engine': eng, 'q': q, 'shows': sh, 'pos': pos,
                                  'rivals': rivals})
for u in cann:
    cann[u].sort(key=lambda x: -x['shows'])
json.dump(cann, open(os.path.join(HERE, 'cannibals.json'), 'w'), ensure_ascii=False)
print('cannibals.json:', len(cann), 'URL с пересечениями')
tot = sum(len(v) for v in cann.values())
print('всего пересечений (показы>=5):', tot)
