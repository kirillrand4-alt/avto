# -*- coding: utf-8 -*-
"""Шаг 1: кого мерить + как искать карточку в 2ГИС.

(a) пересечение sales_base × enrich.db (у кого есть сайт/регион) — это и есть
    пул, на котором меряем;
(b) стратегии запроса к 2ГИС: имя+регион, домен сайта, просто имя;
(c) полная структура contact_groups у найденной карточки — есть ли подписи.
"""
import json
import re
import sqlite3
import sys
import traceback
import urllib.parse
import urllib.request

sys.path.insert(0, r'C:\sender\server')
import enrich_contacts as EC  # noqa: E402
import enrich_db as EDB       # noqa: E402

БАЗА = r'C:\sender\_ops\sales_base.json'
КЛЮЧ = 'ruxlih0718'
ПОЛЯ = ('items.contact_groups,items.address,items.org,items.region_id,'
        'items.locale,items.external_content,items.rubrics')


def P(*a):
    print(*a)
    sys.stdout.flush()


def строки_базы():
    d = json.load(open(БАЗА, encoding='utf-8'))
    out = []
    if isinstance(d, dict):
        for v in d.values():
            if isinstance(v, list):
                out += v
    elif isinstance(d, list):
        out = d
    return out


def гет(u, тайм=20):
    h = {'User-Agent': getattr(EC.VC, 'UA', 'Mozilla/5.0')}
    try:
        r = EC._DIRECT.open(urllib.request.Request(u, headers=h), timeout=тайм)
        return r.read(), r.headers.get('Content-Type', ''), r.status
    except Exception as ex:  # noqa: BLE001
        тело = b''
        try:
            тело = ex.read()[:300]
        except Exception:  # noqa: BLE001
            pass
        return тело, f'ОШИБКА {type(ex).__name__}: {str(ex)[:80]}', 0


def двагис(q):
    u = ('https://catalog.api.2gis.ru/3.0/items?q=' + urllib.parse.quote(q)
         + '&key=' + КЛЮЧ + '&fields=' + ПОЛЯ + '&page_size=5')
    raw, ct, st = гет(u)
    if not raw:
        return None, str(ct)
    txt = EC._раскодировать(raw, ct)
    try:
        d = json.loads(txt)
    except Exception:  # noqa: BLE001
        return None, 'не-JSON: ' + txt[:120]
    код = ((d.get('meta') or {}).get('code'))
    if код != 200:
        return None, f'code={код} {json.dumps(d.get("meta"), ensure_ascii=False)[:140]}'
    return (d.get('result') or {}).get('items') or [], ''


def main():
    строки = строки_базы()
    по_инн = {}
    for x in строки:
        i = str(x.get('inn') or '').strip()
        if i:
            по_инн.setdefault(i, x)
    P('sales_base уникальных ИНН:', len(по_инн))

    con = sqlite3.connect(EDB.DB_PATH)
    cur = con.cursor()
    пул = []
    for inn, x in по_инн.items():
        r = cur.execute(
            'SELECT name, site, region, division FROM companies WHERE inn=?',
            (inn,)).fetchone()
        if not r:
            continue
        имя, сайт, рег, див = (r[0] or ''), (r[1] or ''), (r[2] or ''), (r[3] or '')
        пул.append({'inn': inn, 'name': имя or str(x.get('name') or ''),
                    'site': сайт, 'region': рег, 'division': див,
                    'phones': x.get('phones') or []})
    с_сайтом = [c for c in пул if c['site']]
    P('в enrich.db найдено:', len(пул), '| из них с сайтом:', len(с_сайтом))
    P('пример региона:', json.dumps(с_сайтом[:2], ensure_ascii=False)[:400])

    # ---- стратегии запроса к 2ГИС на первых трёх с сайтом
    for c in с_сайтом[:3]:
        имя = EC.бренд_компании(c['name'], c['site'])
        for метка, q in (('имя+регион', f'{имя} {c["region"]}'.strip()),
                         ('домен', c['site']),
                         ('имя', имя)):
            items, err = двагис(q)
            if items is None:
                P(f'  [{метка}] q={q[:50]!r} -> ОШИБКА {err[:120]}')
                continue
            P(f'  [{метка}] q={q[:50]!r} -> найдено {len(items)}',
              ('| первый: ' + str((items[0].get('name') or ''))[:60]) if items else '')
        P('--- компания', c['inn'], c['name'][:50], 'регион=', c['region'])

    # ---- полная структура карточки: берём заведомо крупный завод
    for проба in ('Криогенмаш Балашиха', 'Уралэлектромедь Верхняя Пышма'):
        items, err = двагис(проба)
        if not items:
            P('проба', проба, '-> пусто', err[:120])
            continue
        it = items[0]
        P('=== проба', проба, '| name=', str(it.get('name'))[:60])
        P('    ключи карточки:', sorted(it.keys()))
        cg = it.get('contact_groups') or []
        P('    contact_groups=', len(cg), json.dumps(cg, ensure_ascii=False)[:900])
        break

    P('ИТОГ: пул=%d с_сайтом=%d' % (len(пул), len(с_сайтом)))


if __name__ == '__main__':
    try:
        main()
    except Exception:  # noqa: BLE001
        P('!! упало:', traceback.format_exc()[-600:].replace('\n', ' | '))
