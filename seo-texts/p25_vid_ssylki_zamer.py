# -*- coding: utf-8 -*-
"""ГЛАЗА НАШЛИ ТО, ЧЕГО СЧЁТЧИК НЕ ПОКАЗЫВАЛ: из четырёх доказавших ссылок ТРИ оказались
СТРАНИЦАМИ ПОИСКА ЕИС (`extendedsearch/results.html?...`), а не карточками закупки.

Разница не косметическая. Страница поиска доказывает «по такому запросу выдача содержит
слово машины». Карточка закупки доказывает «ЭТА закупка ЭТОГО заказчика — про эту машину».
Первое слабее второго ровно настолько, насколько запрос мог быть широким. Мой счётчик обе
считал одинаково — «ДОКАЗЫВАЕТ», — и по нему нельзя отличить крепкое доказательство от
слабого.

Считаю, из чего вообще состоит доказательная база парка, по ВИДУ адреса. Не сужу заранее,
кто «плохой»: сначала показываю доли, потом смотрю глазами по одному примеру каждого вида.
"""
import collections, io, json, os, re, urllib.parse, urllib.request
OPS = r'C:\sender\_ops'
drop = os.environ.get('DROP_URL', '').rstrip('/')
tok = {'X-Drop-Token': os.environ.get('DROP_TOKEN', '')}
op = urllib.request.build_opener(urllib.request.ProxyHandler({}))
VIDY = [
    ('поиск ЕИС (запрос, а не карточка)', re.compile(r'zakupki\.gov\.ru/epz/order/extendedsearch')),
    ('карточка закупки ЕИС', re.compile(r'zakupki\.gov\.ru/epz/order/(notice|orderplan)')),
    ('карточка организации ЕИС', re.compile(r'zakupki\.gov\.ru/epz/organization/')),
    ('поиск на площадке', re.compile(r'(procedures/?\?search|/poisk/search|\?query_field=|\?name=)')),
    ('карточка процедуры площадки', re.compile(r'(etpgpb\.ru/procedure/|tektorg\.ru/.+/procedures/\d|'
                                               r'roseltorg\.ru/procedure|rts-tender\.ru/poisk/id/)')),
    ('заключение ЭПБ (monitor-pb)', re.compile(r'monitor-pb\.ru/conclusion')),
    ('Тендер.Про', re.compile(r'tender\.pro')),
    ('сайт предприятия / прочее', re.compile(r'.')),
]


def stroki(imya):
    p = os.path.join(OPS, imya)
    if os.path.exists(p):
        return io.open(p, encoding='utf-8', errors='replace').read().splitlines()
    try:
        return op.open(urllib.request.Request('%s/%s' % (drop, imya), headers=tok),
                       timeout=300).read().decode('utf-8', 'replace').splitlines()
    except Exception:  # noqa: BLE001
        return []


sch = collections.Counter()
edinstv = collections.Counter()
primery = {}
fakty = 0
for f in ['park_ingest_3.jsonl', 'park_ingest_3b.jsonl', 'park_ingest_3c.jsonl',
          'park_ingest_3d.jsonl', 'PARK-PLOSHCHADKI-DLYA-PARKA-3S.jsonl',
          'PARK-RTS-PODTV-3S.jsonl']:
    for s in stroki(f):
        try: z = json.loads(s)
        except Exception: continue
        us = [u for u in str(z.get('istochniki') or '').split(' | ') if u.startswith('http')]
        if not us:
            continue
        fakty += 1
        vidy_fakta = set()
        for u in us:
            for imya, rx in VIDY:
                if rx.search(u):
                    sch[imya] += 1
                    vidy_fakta.add(imya)
                    primery.setdefault(imya, u)
                    break
        if len(vidy_fakta) == 1:
            edinstv[list(vidy_fakta)[0]] += 1
print('########## ИЗ ЧЕГО СОСТОИТ ДОКАЗАТЕЛЬНАЯ БАЗА ПАРКА (фактов со ссылками %d)' % fakty)
print('  %-38s %8s %10s' % ('вид адреса', 'ссылок', 'фактов, где ТОЛЬКО он'))
for imya, _ in VIDY:
    print('  %-38s %8d %10d' % (imya, sch.get(imya, 0), edinstv.get(imya, 0)))
slab = edinstv.get('поиск ЕИС (запрос, а не карточка)', 0) + edinstv.get('поиск на площадке', 0)
print('  --- ФАКТОВ, ДЕРЖАЩИХСЯ ТОЛЬКО НА СТРАНИЦЕ ПОИСКА: %d (%.1f%%)'
      % (slab, 100.0 * slab / max(1, fakty)))
print('  --- по одному примеру каждого вида, глазами')
for imya, _ in VIDY:
    if imya in primery:
        print('     %-38s %s' % (imya[:38], primery[imya][:100]))
print('ИТОГ ' + json.dumps({'фактов': fakty, 'только поиск': slab}, ensure_ascii=False))
