# -*- coding: utf-8 -*-
r"""fixKO (21.10): данные панели КЦ для плана «главная списком» и список ИНН для владельца. Только чтение.

Снимки баз КЦ (centro_sales.db, centrifugal.db) – sqlite backup во временный каталог; код панели
импортируется под venv КЦ с путями к снимкам, живые базы не открываются на запись. Выдаёт:
  * колонки таблицы company каталога и заполненность полей, нужных колонкам списка;
  * сводку «что показывает панель»: в каталоге, скрыто, по менеджерам и вкладкам;
  * на дроп `KO-inn-ne-v-rabote-<дата>.csv` – компании, которые панель показывает (в каталоге, не скрыты),
    кроме «Взял в работу»: ИНН, название, регион, менеджер, вкладка/статус, сайт. Без телефонов.

    python3 zapusk_na_servere.py fixKO_dannye.py
"""
import csv
import io
import json
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
    from app.services import centro_sales as sales
    companies, version, _info = rcs._source_companies()
    hidden = sales.hidden_companies()
    s = sqlite3.connect('file:%s?mode=ro' % os.environ['CENTRO_SALES_DB'], uri=True)
    s.row_factory = sqlite3.Row
    asg = {r['inn']: dict(r) for r in s.execute('SELECT * FROM company_assignment')}
    st = {(r['inn'], r['username']): dict(r) for r in s.execute('SELECT * FROM company_state')}
    k = sqlite3.connect('file:%s?mode=ro' % os.environ['CENTRIFUGAL_DB'], uri=True)
    kol = [r[1] for r in k.execute('PRAGMA table_info(company)')]
    zapoln = {}
    for c in kol:
        zapoln[c] = k.execute('SELECT COUNT(*) FROM company WHERE COALESCE(TRIM(CAST("%s" AS TEXT)),\'\') NOT IN (\'\',\'0\')' % c).fetchone()[0]
    print('каталог: строк company %d, колонок %d, версия %s' % (k.execute('SELECT COUNT(*) FROM company').fetchone()[0], len(kol), version))
    print('колонки (заполнено):', ', '.join('%s=%d' % (c, zapoln[c]) for c in kol))
    nuzhno = ('predpriyatie', 'name_short', 'region', 'okved', 'vyruchka_rub', 'tipy_mashin', 'marki', 'n_phones', 'n_tech',
              'n_purchaser', 'status_egrul', 'sayt', 'website')
    print('для списка:', {c: sum(1 for x in companies if x.get(c) not in (None, '', 0)) for c in nuzhno})
    print('после слияния: компаний %d, has_phone %d, has_role_phone %d, has_tech %d, has_purchaser %d, verdikt %d, pod_zamenu %d' % (
        len(companies), sum(1 for x in companies if x['has_phone']), sum(1 for x in companies if x['has_role_phone']),
        sum(1 for x in companies if x['has_tech']), sum(1 for x in companies if x['has_purchaser']),
        sum(1 for x in companies if x['verdikt']), sum(1 for x in companies if x['pod_zamenu'])))
    print('статусы ЕГРЮЛ:', sorted({str(x.get('status_egrul') or '') for x in companies})[:15])
    vidno, svodka, vne = [], {}, 0
    for x in companies:
        if x['inn'] in hidden:
            continue
        a = asg.get(x['inn'])
        u = a['username'] if a else ''
        sost = st.get((x['inn'], u), {}) if a else {}
        rez = sost.get('call_result') or 'new'
        vkl = sales.CALL_RESULT_CHOICES.get(rez, 'Вся очередь' + ('' if rez == 'new' else ' (%s)' % sales.CALL_RESULT_LABELS.get(rez, rez)))
        svodka[(u or '—', vkl)] = svodka.get((u or '—', vkl), 0) + 1
        y = dict(x)
        y.update(assigned_user=u, assignment_score=(a or {}).get('assignment_score', 0), call_result=rez,
                 next_contact_at=sost.get('next_contact_at'), _vkl=vkl)
        vidno.append(y)
    inn_kat = {x['inn'] for x in companies}
    print('скрыто целиком: %d (из них в каталоге %d); показывается: %d' % (
        len(hidden), sum(1 for i in hidden if i in inn_kat), len(vidno)))
    print('назначений: %d, из них нет в каталоге: %d' % (len(asg), sum(1 for i in asg if i not in inn_kat)))
    for (u, v), n in sorted(svodka.items()):
        print('   %-10s %-40s %d' % (u, v, n))
    vidno.sort(key=lambda c: (c['assigned_user'] or 'яя', rcs._queue_rank(c)))
    put = os.path.join(DROP, 'KO-inn-ne-v-rabote-%s.csv' % time.strftime('%Y%m%d'))
    n = s_saytom = 0
    with io.open(put, 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.writer(f, delimiter=';')
        w.writerow(['№', 'ИНН', 'Компания', 'Регион', 'Менеджер', 'Вкладка / статус', 'Сайт'])
        for c in vidno:
            if c['call_result'] == 'v_rabote':
                continue
            n += 1
            sayt = str(c.get('sayt') or c.get('website') or '').strip()
            s_saytom += bool(sayt)
            w.writerow([n, c['inn'], c.get('predpriyatie') or c.get('name_short') or c.get('name_full') or '',
                        c.get('region') or '', c['assigned_user'] or 'не назначена', c['_vkl'], sayt])
    print('CSV: %s – строк %d, с сайтом %d' % (put, n, s_saytom))
    raise SystemExit(0)

# ---------------------------------------------------------------- снаружи: снимки баз и запуск под venv
STAGE = os.path.join(KOREN, '_stage', 'fixKO-dannye-' + T)
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
    r = subprocess.run([VENV, os.path.abspath(__file__), '--vnutri'], cwd=KOREN, env=env, capture_output=True, timeout=900)
    print(r.stdout.decode('utf-8', 'replace')[-5500:])
    if r.returncode:
        print('rc=%s\n%s' % (r.returncode, r.stderr.decode('utf-8', 'replace')[-2500:]))
finally:
    shutil.rmtree(STAGE, ignore_errors=True)
