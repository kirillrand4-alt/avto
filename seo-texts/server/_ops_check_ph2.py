# -*- coding: utf-8 -*-
"""Целостность привязки кэша к ИНН для партии переразметки 2026-07-29.

Три теста:
1) имя файла кэша <ИНН>.json.gz vs ИНН, под который записаны телефоны;
2) домены страниц внутри кэша vs companies.site того же ИНН — если кэш
   набит чужим доменом, все телефоны уехали не туда;
3) объёмы почт (+90).
"""
import gzip
import io
import json
import os
import re
import sys

sys.path.insert(0, r'C:\sender\server')
import enrich_db as EDB  # noqa: E402

e = EDB.EnrichDB().cx
КЭШ = r'C:\seostat\drop\pagecache'
ПОТОК = r'C:\seostat\drop\pagecache_roles.jsonl'


def dom(u):
    u = str(u or '').strip().lower()
    u = re.sub(r'^https?://', '', u).split('/')[0].split(':')[0]
    return u[4:] if u.startswith('www.') else u


def core(d):
    p = [x for x in d.split('.') if x]
    return '.'.join(p[-2:]) if len(p) >= 2 else d


def тест1():
    if not os.path.exists(ПОТОК):
        print('  потока нет')
        return set()
    плохие = set()
    сов = раз = 0
    for ln in io.open(ПОТОК, encoding='utf-8', errors='replace'):
        try:
            x = json.loads(ln)
        except Exception:  # noqa: BLE001
            continue
        имя = str(x.get('файл') or '')
        m = re.match(r'(\d{10}|\d{12})', имя)
        if not m or not x.get('inn'):
            continue
        if m.group(1) == str(x['inn']):
            сов += 1
        else:
            раз += 1
            плохие.add(str(x['inn']))
            if раз <= 12:
                print('   РАЗЪЕХАЛОСЬ файл=%s -> записано_под_инн=%s'
                      % (имя, x['inn']))
    print('  тест1: совпало=%d разъехалось=%d уник_чужих_инн=%d'
          % (сов, раз, len(плохие)))
    return плохие


def тест2():
    inns = [r[0] for r in e.execute(
        "SELECT DISTINCT inn FROM phone_contacts WHERE source='сайт компании' "
        "AND updated_at LIKE '2026-07-29%'").fetchall()]
    ок = чуж = нет = 0
    примеры = []
    for inn in inns:
        p = os.path.join(КЭШ, '%s.json.gz' % inn)
        if not os.path.exists(p):
            нет += 1
            continue
        try:
            d = json.loads(gzip.open(p, 'rb').read().decode('utf-8', 'replace'))
        except Exception:  # noqa: BLE001
            нет += 1
            continue
        pages = d.get('pages') or []
        домены = set(core(dom(pg.get('url'))) for pg in pages if pg.get('url'))
        site = (e.execute('SELECT site FROM companies WHERE inn=?',
                          (inn,)).fetchone() or [''])[0]
        s = core(dom(site))
        if not s:
            нет += 1
            continue
        if s in домены:
            ок += 1
            if len(домены) > 1:
                примеры.append({'инн': inn, 'сайт': s,
                                'лишние_домены': sorted(домены - {s})[:4]})
        else:
            чуж += 1
            примеры.append({'инн': inn, 'сайт_карточки': s, 'ЧУЖОЙ': True,
                            'домены_кэша': sorted(домены)[:4],
                            'имя': (e.execute(
                                'SELECT name FROM companies WHERE inn=?',
                                (inn,)).fetchone() or [''])[0][:40]})
    print('  тест2: компаний=%d домен_свой=%d ЧУЖОЙ=%d без_кэша/сайта=%d'
          % (len(inns), ок, чуж, нет))
    for x in примеры[:12]:
        print('   ', json.dumps(x, ensure_ascii=False)[:260])


def тест3():
    tabs = [r[0] for r in e.execute(
        "SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
    print('  таблицы:', ','.join(tabs))
    if 'email_contacts' in tabs:
        print('  cols:', ','.join(
            r[1] for r in e.execute(
                'PRAGMA table_info(email_contacts)').fetchall()))
        for r in e.execute(
                'SELECT source, COUNT(*), COUNT(DISTINCT inn), '
                'substr(MAX(updated_at),1,10) FROM email_contacts GROUP BY '
                'source ORDER BY 2 DESC').fetchall()[:12]:
            print('   %-20s n=%-5s инн=%-4s посл=%s' % r)
        for r in e.execute(
                "SELECT substr(updated_at,1,10) d, COUNT(*) FROM "
                "email_contacts WHERE source LIKE '%сайт%' GROUP BY d "
                "ORDER BY d").fetchall()[-6:]:
            print('   почты сайт %s n=%s' % r)


if __name__ == '__main__':
    print('=== ТЕСТ1 имя файла vs ИНН ===')
    тест1()
    print('=== ТЕСТ2 домены кэша vs сайт компании ===')
    тест2()
    print('=== ТЕСТ3 почты ===')
    тест3()
