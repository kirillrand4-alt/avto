# -*- coding: utf-8 -*-
"""Ссылки в парковом потоке помечаются ПО ВИДУ: доказательство, поиск-как-искали, карточка.

1-я сессия влила мой `park_ingest_3d.jsonl` и нашла в нём дефект, который я не назвала:
среди `istochniki` лежат адреса вида

    zakupki.gov.ru/epz/order/extendedsearch/results.html?searchString=компрессорная станция&…

Это «как мы искали», а не «вот машина ЭТОГО предприятия». Она права, и претензию я
принимаю. Но её мерка сложила в одну кучу два разных адреса, и это важно, потому что
второй — полноценное доказательство:

    ?searchString=0131200001026003    поиск ПО РЕЕСТРОВОМУ НОМЕРУ извещения. Прямой путь
                                      к карточке 404-ит (проверено на 20 адресах), и эта
                                      форма — единственная рабочая постоянная ссылка на
                                      КОНКРЕТНОЕ извещение.
    ?searchString=компрессорная…      поиск ПО СЛОВУ. Доказывает только способ поиска.

Замер по моему потоку (`park_ingest_3d.jsonl`, 1 118 строк, 5 054 ссылки):

    по номеру извещения ......... 1 999
    по слову («как искали») ..... 1 923
    карточка организации ........ 1 132
    строк со ссылкой на конкретное извещение ....... 1 118 из 1 118
    строк, где ВСЕ ссылки только поисковые по слову ....... 0

То есть ни одна строка не держится на «как искали» — но пометки на этих адресах не было,
и по виду они неотличимы. Здесь я её и ставлю: каждая ссылка получает свой вид, и в поток
добавляются два поля — `ssylki_dokazatelstva` (только те, что доказывают поштучно) и
`ssylki_kak_iskali`. Ничего не удаляю: способ поиска — тоже провенанс, он говорит, откуда
взялась строка.

Числа в КОНЦЕ.
"""
import collections
import io
import json
import os
import re
import urllib.request

OPS = r'C:\sender\_ops'
FAJLY = ['park_ingest_3d.jsonl']
PO_NOMERU = re.compile(r'searchString=\d{11,25}')
POISK = re.compile(r'extendedsearch/results\.html|/search/results\.html')
KARTOCHKA = re.compile(r'organization/view')
drop = os.environ.get('DROP_URL', '').rstrip('/')
tok = {'X-Drop-Token': os.environ.get('DROP_TOKEN', '')}
op = urllib.request.build_opener(urllib.request.ProxyHandler({}))

svod = collections.Counter()
for f in FAJLY:
    put = os.path.join(OPS, f)
    if not os.path.exists(put):
        svod['НЕТ ФАЙЛА: %s' % f] += 1
        continue
    stroki = []
    for s in io.open(put, encoding='utf-8'):
        try:
            o = json.loads(s)
        except Exception:  # noqa: BLE001
            continue
        us = [u for u in str(o.get('istochniki') or '').split(' | ') if u.startswith('http')]
        dok, kak, kart = [], [], []
        for u in us:
            if PO_NOMERU.search(u):
                dok.append(u)
            elif POISK.search(u):
                kak.append(u)
            elif KARTOCHKA.search(u):
                kart.append(u)
            else:
                dok.append(u)
        o['ssylki_dokazatelstva'] = ' | '.join(dok)
        o['ssylok_dokazatelstv'] = len(dok)
        o['ssylki_kak_iskali'] = ' | '.join(kak)
        o['ssylka_kartochki_organizacii'] = ' | '.join(kart)
        o['dokazatelstvo_est'] = bool(dok)
        svod['ссылок-доказательств'] += len(dok)
        svod['ссылок «как искали»'] += len(kak)
        svod['ссылок на карточку организации'] += len(kart)
        svod['строк с поштучным доказательством' if dok
             else 'СТРОК БЕЗ поштучного доказательства'] += 1
        stroki.append(o)
    with io.open(put, 'w', encoding='utf-8') as g:
        for o in stroki:
            g.write(json.dumps(o, ensure_ascii=False) + '\n')
    try:
        rq = urllib.request.Request('%s/%s' % (drop, f),
                                    data=io.open(put, 'rb').read(), method='PUT', headers=tok)
        svod['выложено %s' % f] = 1
        op.open(rq, timeout=300).read()
    except Exception as e:  # noqa: BLE001
        print('НЕ ВЫЛОЖЕН %s: %s' % (f, str(e)[:60]))

print('\n\n########## ЧИСЛА')
for k, v in svod.most_common():
    print('  %-46s %6d' % (k[:46], v))
print('ИТОГ ' + json.dumps({k: v for k, v in svod.items()}, ensure_ascii=False))
