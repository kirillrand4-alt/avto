# -*- coding: utf-8 -*-
"""Каждому факту — ССЫЛКА, ДОКАЗЫВАЮЩАЯ ИНН. Дыру нашла чужая мерка.

1-я сессия меряет строго: показывает ли ЛУЧШАЯ ссылка И машину, И ИНН. У них 53 %, у меня
вышло 0 из 20 — и это не дефект прибора (перемерила браузером тем же жребием) и не слабые
данные. Причина в устройстве ЕИС: **извещение не печатает ИНН заказчика**, там только
название; ИНН живёт на карточке организации — отдельной странице.

Замер дыры по живым файлам:

    фактов с ИНН и ссылкой                    11 947
    рядом лежит карточка организации           2 806  (23 %) — только park_ingest_3d
    у потоков 3, 3b, 3c такой ссылки нет ни у одной строки

То есть у 9 141 факта ИНН доказан лишь тем, что он был снят с карточки в момент сбора, а
ссылки на неё в строке не осталось. Это ровно то, за что я цепляюсь у других: «поле
заполнено» не равно «факт доказан».

ЧТО ДЕЛАЮ. Дописываю каждому такому факту `ssylka_inn` — поиск организаций ЕИС по ИНН:

    https://zakupki.gov.ru/epz/organization/search/results.html?searchString=<ИНН>

Форма проверена пробой с сервера на ПАО «ЮГК» (7424024375): страница отдаёт 200, на ней
видны И ИНН, И название. Ссылка детерминированная — один ИНН, одна организация.

ЧЕСТНАЯ ГРАНИЦА, и она записывается в саму строку: эта ссылка доказывает, что ИНН
принадлежит организации С ТАКИМ НАЗВАНИЕМ. Что именно эта организация — заказчик той
закупки, доказывает первая ссылка (извещение с названием заказчика). Цепочка из двух
звеньев названа явно, чтобы никто — включая меня — не выдал одно звено за оба.

Числа в КОНЦЕ.
"""
import collections
import io
import json
import os
import re
import urllib.request

OPS = r'C:\sender\_ops'
FAJLY = ['park_ingest_3.jsonl', 'park_ingest_3b.jsonl', 'park_ingest_3c.jsonl',
         'park_ingest_3d.jsonl']
ORG = re.compile(r'/epz/organization/(view|search)', re.I)
FORMA = 'https://zakupki.gov.ru/epz/organization/search/results.html?searchString=%s'
drop = os.environ.get('DROP_URL', '').rstrip('/')
tok = {'X-Drop-Token': os.environ.get('DROP_TOKEN', '')}
op = urllib.request.build_opener(urllib.request.ProxyHandler({}))

svod = collections.Counter()
for f in FAJLY:
    put = os.path.join(OPS, f)
    if not os.path.exists(put):
        svod['НЕТ ФАЙЛА: %s' % f] += 1
        continue
    stroki, dopisano = [], 0
    for s in io.open(put, encoding='utf-8'):
        try:
            o = json.loads(s)
        except Exception:  # noqa: BLE001
            continue
        inn = str(o.get('inn') or '').strip()
        us = [u for u in str(o.get('istochniki') or '').split(' | ') if u.startswith('http')]
        us += [u for u in str(o.get('ssylka_kartochki_organizacii') or '').split(' | ')
               if u.startswith('http')]
        if inn.isdigit() and not any(ORG.search(u) for u in us):
            o['ssylka_inn'] = FORMA % inn
            o['chto_dokazyvaet_ssylka_inn'] = ('ИНН принадлежит организации с этим названием; '
                                               'что она заказчик закупки — доказывает ссылка '
                                               'на извещение')
            dopisano += 1
        stroki.append(o)
    with io.open(put, 'w', encoding='utf-8') as g:
        for o in stroki:
            g.write(json.dumps(o, ensure_ascii=False) + '\n')
    svod['%s: строк' % f] = len(stroki)
    svod['%s: дописана ссылка на ИНН' % f] = dopisano
    try:
        rq = urllib.request.Request('%s/%s' % (drop, f),
                                    data=io.open(put, 'rb').read(), method='PUT', headers=tok)
        op.open(rq, timeout=300).read()
        svod['%s: выложен' % f] = 1
    except Exception as e:  # noqa: BLE001
        print('НЕ ВЫЛОЖЕН %s: %s' % (f, str(e)[:60]))

print('\n\n########## ЧИСЛА')
for k, v in svod.most_common():
    print('  %-52s %6d' % (k[:52], v))
print('ИТОГ ' + json.dumps(dict(svod), ensure_ascii=False))
