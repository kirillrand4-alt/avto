# -*- coding: utf-8 -*-
r"""fixKI (22.10): панель КЦ – контакты видимых компаний по источникам. Только чтение (снимки баз во временный каталог).

Видимые компании – как в панели: есть в каталоге и не скрыты целиком. Контакты – как в карточке: catalog.contacts(inn),
без номеров, которые продавец убрал у компании (hidden_item kind=phone). Источник – домен ссылки source_url (несколько ссылок –
контакт считается у каждого домена и отдельно «по первому»), без ссылки – подпись source. Номера и адреса почты не выводятся.
Сводка – stdout и дроп `KI-istochniki-<дата>.json`.

    python3 zapusk_na_servere.py fixKI_istochniki.py
"""
import collections
import io
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import time

KOREN = r'C:\seostat'
VENV = r'C:\seostat\.venv\Scripts\python.exe'
DATA = os.path.join(KOREN, 'data')
DROP = r'C:\seostat\drop\drop-storage'
T = time.strftime('%Y%m%d-%H%M%S')


def domen(url):
    m = re.match(r'https?://([^/?#\s]+)', url.strip(), re.I)
    return m.group(1).lower().removeprefix('www.') if m else ''


if len(sys.argv) > 1 and sys.argv[1] == '--vnutri':
    sys.path.insert(0, KOREN)
    from app.api import routes_centro_sales as rcs
    from app.services import centro_catalog as catalog
    from app.services import centro_sales as sales
    companies, _v, _i = rcs._source_companies()
    hidden = sales.hidden_companies()
    s = sqlite3.connect('file:%s?mode=ro' % os.environ['CENTRO_SALES_DB'], uri=True)
    asg = dict(s.execute('SELECT inn, username FROM company_assignment').fetchall())
    skryt_nom = collections.defaultdict(set)
    for inn, val in s.execute("SELECT inn, value FROM hidden_item WHERE kind='phone'"):
        skryt_nom[str(inn)].add(str(val))
    vidno = [c for c in companies if c['inn'] not in hidden]
    agg = collections.defaultdict(lambda: {'n': 0, 'inn': set(), 'sayt': 0, 'chelovek': 0, 'rol': 0, 'obshchiy': 0,
                                           'tip': collections.Counter(), 'ne_lich': 0, 'inn_sayt': set()})
    perv = collections.defaultdict(lambda: {'n': 0, 'inn': set()})
    vsego = collections.Counter()
    kolonki = set()
    po_men = collections.Counter()
    for c in vidno:
        sayt = domen('http://' + re.sub(r'^https?://', '', str(c.get('sayt') or '').strip())) if c.get('sayt') else ''
        for k in catalog.contacts(c['inn']):
            kolonki.update(k.keys())
            vid = k['kind'] or 'другое'
            if vid == 'phone' and k['value'] in skryt_nom.get(c['inn'], ()):
                vsego['убрано продавцом'] += 1
                continue
            urls = [u for u in re.split(r'[;\s]+', k.get('source_url') or '') if u.startswith('http')]
            dom = list(dict.fromkeys(domen(u) for u in urls if domen(u)))
            klyuchi = dom or ['без ссылки: ' + ((k.get('source') or '').split(';')[0].strip() or 'источник не указан')]
            vsego[vid] += 1
            vsego['всего'] += 1
            po_men[(asg.get(c['inn'], '—'), vid)] += 1
            if len(klyuchi) > 1:
                vsego['несколько источников'] += 1
            for i, kl in enumerate(klyuchi):
                a = agg[(vid, kl)]
                a['n'] += 1
                a['inn'].add(c['inn'])
                a['sayt'] += bool(sayt) and (kl == sayt or kl.endswith('.' + sayt))
                a['chelovek'] += bool(k.get('person'))
                a['rol'] += bool(k.get('has_role'))
                a['obshchiy'] += bool(k.get('is_unknown_owner'))
                a['tip'][str(k.get('phone_type') or '').strip() or '—'] += 1
                a['ne_lich'] += bool(str(k.get('nomer_ne_lichnyy') or '').strip())
                if bool(sayt) and (kl == sayt or kl.endswith('.' + sayt)):
                    a['inn_sayt'].add(c['inn'])
                if i == 0:
                    perv[(vid, kl)]['n'] += 1
                    perv[(vid, kl)]['inn'].add(c['inn'])
    rez = {'kompaniy_vidno': len(vidno), 'kompaniy_s_kontaktami': len({i for a in agg.values() for i in a['inn']}),
           'vsego': dict(vsego), 'po_menedzheram': {'%s %s' % k: n for k, n in po_men.items()},
           'kolonki_contact': sorted(kolonki),
           'istochniki': [{'vid': v, 'istochnik': kl, 'kontaktov': a['n'], 'kompaniy': len(a['inn']), 'sayt_kompanii': a['sayt'],
                           's_chelovekom': a['chelovek'], 's_rolyu': a['rol'], 'obshchiy_nomer': a['obshchiy'],
                           'po_pervomu': perv[(v, kl)]['n'], 'tip': dict(a['tip'].most_common(6)), 'ne_lichnyy': a['ne_lich'],
                           'inn': sorted(a['inn']), 'inn_sayt': sorted(a['inn_sayt'])}
                          for (v, kl), a in sorted(agg.items(), key=lambda x: -x[1]['n'])]}
    put = os.path.join(DROP, 'KI-istochniki-%s.json' % time.strftime('%Y%m%d'))
    io.open(put, 'w', encoding='utf-8').write(json.dumps(rez, ensure_ascii=False, indent=1))
    print('видимых компаний %d, с контактами %d; контакты: %s' % (rez['kompaniy_vidno'], rez['kompaniy_s_kontaktami'], rez['vsego']))
    print('по менеджерам:', rez['po_menedzheram'])
    print('колонки contact:', rez['kolonki_contact'])
    for x in rez['istochniki'][:12]:
        print('%-6s %-45s конт %5d комп %4d сайт-комп %4d чел %4d роль %4d общий %4d первый %5d' % (
            x['vid'], x['istochnik'][:45], x['kontaktov'], x['kompaniy'], x['sayt_kompanii'], x['s_chelovekom'], x['s_rolyu'],
            x['obshchiy_nomer'], x['po_pervomu']))
    print('источников всего: %d; файл %s' % (len(rez['istochniki']), put))
    raise SystemExit(0)

STAGE = os.path.join(KOREN, '_stage', 'fixKI-' + T)
os.makedirs(STAGE, exist_ok=True)
try:
    puti = {}
    for imya in ('centro_sales.db', 'centrifugal.db'):
        a = sqlite3.connect('file:%s?mode=ro' % os.path.join(DATA, imya), uri=True, timeout=30)
        b = sqlite3.connect(os.path.join(STAGE, imya))
        a.backup(b)
        b.close()
        a.close()
        puti[imya] = os.path.join(STAGE, imya)
    env = {x: v for x, v in os.environ.items() if not x.startswith(('CENTRO', 'PARK_', 'OBZVON', 'CENTRIFUGAL'))}
    env.update(PYTHONIOENCODING='utf-8', PYTHONDONTWRITEBYTECODE='1', PYTHONPATH=KOREN, OBZVON_ROOT_PATH='/obzvon',
               CENTRO_SALES_DB=puti['centro_sales.db'], CENTRIFUGAL_DB=puti['centrifugal.db'], CENTRO_DB=puti['centrifugal.db'],
               PARK_OCHERED_SALES_DB=puti['centro_sales.db'], PARK_OCHERED_DB=puti['centrifugal.db'],
               PARK_PANEL_DB=os.path.join(STAGE, 'net-park.db'), CENTRO_SESSION_SECRET='x' * 40)
    r = subprocess.run([VENV, os.path.abspath(__file__), '--vnutri'], cwd=KOREN, env=env, capture_output=True, timeout=1200)
    print(r.stdout.decode('utf-8', 'replace')[-5800:])
    if r.returncode:
        print('rc=%s\n%s' % (r.returncode, r.stderr.decode('utf-8', 'replace')[-2500:]))
finally:
    shutil.rmtree(STAGE, ignore_errors=True)
