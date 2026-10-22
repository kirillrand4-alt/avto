# -*- coding: utf-8 -*-
r"""fixKF (22.10): панель КЦ – компании, у которых блок «Оборудование – что уже известно» пустой (ни одного показанного факта
об использовании воздушного центробежного компрессора). Только чтение (снимки баз во временный каталог).

Факты – как в карточке: catalog.facts(inn), если пусто – _fallback_fact(компания); «показан» = не отсеян как «не наша машина»
(rejected) и не убран продавцом (hidden_item kind=fact). Объёмные (rejected = ne_centrobezhnaya) – отдельным счётом «+N».
Список кандидатов – на дроп KF-bez-oborudovaniya-<дата>.csv (ИНН, название, регион, менеджер, вкладка, метка Битрикса).

    python3 zapusk_na_servere.py fixKF_razvedka.py
"""
import collections
import csv
import io
import os
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

if len(sys.argv) > 1 and sys.argv[1] == '--vnutri':
    sys.path.insert(0, KOREN)
    from app.api import routes_centro_sales as rcs
    from app.services import centro_catalog as catalog
    from app.services import centro_sales as sales
    companies, _v, _i = rcs._source_companies()
    hidden = sales.hidden_companies()
    s = sqlite3.connect('file:%s?mode=ro' % os.environ['CENTRO_SALES_DB'], uri=True)
    asg = dict(s.execute('SELECT inn, username FROM company_assignment').fetchall())
    sost = {(r[0], r[1]): r[2] for r in s.execute('SELECT inn, username, call_result FROM company_state')}
    skr_fakty = collections.defaultdict(set)
    for inn, val in s.execute("SELECT inn, value FROM hidden_item WHERE kind='fact'"):
        skr_fakty[str(inn)].add(str(val))
    itog = collections.Counter()
    itog2 = collections.Counter()
    kandidaty, kandidaty2 = [], []
    for c in companies:
        if c['inn'] in hidden:
            continue
        f = catalog.facts(c['inn']) or rcs._fallback_fact(c)
        pokaz = [x for x in f if not x.get('rejected') and str(x.get('id') or '') not in skr_fakty[c['inn']]]
        obem = sum(1 for x in f if x.get('rejected') == 'ne_centrobezhnaya')
        musor = sum(1 for x in f if x.get('rejected') and x.get('rejected') != 'ne_centrobezhnaya')
        u = asg.get(c['inn'], '')
        rez = sost.get((c['inn'], u)) or 'new'
        vkl = sales.CALL_RESULT_CHOICES.get(rez, 'Вся очередь')
        itog['видимых'] += 1
        if pokaz:
            itog['с показанными фактами'] += 1
            sredy = collections.Counter(str(x.get('medium') or '').strip().lower() or '—' for x in pokaz)
            vozduh = sum(n for m_, n in sredy.items() if 'воздух' in m_)
            gr2 = 'есть факт про воздух' if vozduh else ('только «не установлено»/пусто' if all(
                m_ in ('—', 'не установлено', 'не установлена', 'неизвестно') for m_ in sredy) else 'только другие среды')
            itog['показаны, по среде: ' + gr2] += 1
            for m_, n in sredy.items():
                itog2[m_[:40]] += n
            if gr2 != 'есть факт про воздух':
                itog['показаны, но не про воздух, вкладка: ' + vkl] += 1
                kandidaty2.append([c['inn'], c.get('predpriyatie') or '', c.get('region') or '', u, vkl, gr2, len(pokaz),
                                   ' | '.join('%s ×%d' % kv for kv in sredy.most_common(4)), c.get('bitrix_metka') or ''])
            continue
        gr = 'только объёмные (+N)' if obem else ('только отсеянные' if musor else 'фактов нет вовсе')
        itog['пусто: ' + gr] += 1
        itog['пусто, вкладка: ' + vkl] += 1
        itog['пусто, менеджер: ' + (u or '—')] += 1
        itog['пусто, метка Битрикса: ' + (c.get('bitrix_metka') or 'нет')] += 1
        kandidaty.append([c['inn'], c.get('predpriyatie') or '', c.get('region') or '', u, vkl, gr, obem, musor,
                          c.get('bitrix_metka') or '', (c.get('prioritet_pochemu') or '')[:120]])
    for k in sorted(itog):
        print('  %-48s %d' % (k, itog[k]))
    put = os.path.join(DROP, 'KF-bez-oborudovaniya-%s.csv' % time.strftime('%Y%m%d'))
    with io.open(put, 'w', encoding='utf-8-sig', newline='') as fh:
        w = csv.writer(fh, delimiter=';')
        w.writerow(['ИНН', 'Компания', 'Регион', 'Менеджер', 'Вкладка', 'Что в блоке', 'Объёмных', 'Отсеянных',
                    'Метка Битрикса', 'Почему звонить (из базы)'])
        w.writerows(kandidaty)
    print('CSV: %s, строк %d' % (put, len(kandidaty)))
    print('среда у показанных фактов (все компании):', itog2.most_common(15))
    put2 = os.path.join(DROP, 'KF-ne-pro-vozduh-%s.csv' % time.strftime('%Y%m%d'))
    with io.open(put2, 'w', encoding='utf-8-sig', newline='') as fh:
        w = csv.writer(fh, delimiter=';')
        w.writerow(['ИНН', 'Компания', 'Регион', 'Менеджер', 'Вкладка', 'Что в блоке', 'Показано фактов', 'Среды фактов', 'Метка Битрикса'])
        w.writerows(kandidaty2)
    print('CSV: %s, строк %d' % (put2, len(kandidaty2)))
    raise SystemExit(0)

STAGE = os.path.join(KOREN, '_stage', 'fixKF-' + T)
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
