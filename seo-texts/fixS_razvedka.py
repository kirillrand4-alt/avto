# -*- coding: utf-8 -*-
"""fixS: только чтение. Разведка перед метками Битрикса «КЦ / СЦ / Meyer провалено»:
  * колонки bitrix_* каталога и их заполненность; компании панели (ИНН, название, регион, страна, поля Битрикса,
    менеджер, ступень, балл) – на дроп fixS-razvedka-kompanii.json (без телефонов) для локальной сверки;
  * meyer4: строк в списке очереди 269, а в CSV 270 – какая компания лишняя и почему (TestClient на КОПИЯХ баз).
    python3 zapusk_na_servere.py fixS_razvedka.py
"""
import collections
import io
import json
import os
import re
import sqlite3
import subprocess
import sys
import time

VENV = r'C:\seostat\.venv\Scripts\python.exe'
KOREN = r'C:\centro2'
KAT = os.path.join(KOREN, 'data', 'meyer_baza1.db')
SALES = os.path.join(KOREN, 'data', 'centro_sales_meyer1.db')
DROP = r'C:\seostat\drop\drop-storage'
PUT = '/obzvon-meyer'


def kopiya(src_put, dst_put):
    src = sqlite3.connect('file:%s?mode=ro' % src_put, uri=True)
    dst = sqlite3.connect(dst_put)
    src.backup(dst)
    dst.close()
    src.close()


def razvedka():
    k = sqlite3.connect('file:%s?mode=ro' % KAT, uri=True)
    k.row_factory = sqlite3.Row
    kol = [r[1] for r in k.execute('PRAGMA table_info(company)')]
    bx = [c for c in kol if 'bitrix' in c or c in ('strana', 'pometka_ocheredi', 'stupen_prichina')]
    print('company: колонки Битрикса и пр.:', ', '.join(bx))
    komp = {r['inn']: dict(r) for r in k.execute('SELECT * FROM company')}
    s = sqlite3.connect('file:%s?mode=ro' % SALES, uri=True)
    s.row_factory = sqlite3.Row
    nazn = {r['inn']: dict(r) for r in s.execute('SELECT * FROM company_assignment')}
    print('компаний %d, назначений %d, без назначения %d, назначений без компании %d' % (
        len(komp), len(nazn), len(set(komp) - set(nazn)), len(set(nazn) - set(komp))))
    print('по менеджерам:', dict(sorted(collections.Counter(a['username'] for a in nazn.values()).items())))
    for c in ('bitrix_kc', 'bitrix_klient_sc', 'bitrix_klient_meyer', 'bitrix_v_rabote'):
        if c in kol:
            print('  %s: заполнено %d' % (c, sum(1 for x in komp.values() if str(x.get(c) or '') not in ('', '0', '0.0', 'None'))))
    print('  bitrix_istochnik:', dict(collections.Counter(str(x.get('bitrix_istochnik')) for x in komp.values())))
    print('ступени:', dict(collections.Counter(a.get('stupen_ocheredi') for a in nazn.values())))
    skr = [dict(r) for r in s.execute("SELECT * FROM hidden_item WHERE kind='company'")]
    print('скрытых компаний: %d' % len(skr))
    for r in skr:
        a = nazn.get(str(r['inn'])) or {}
        print('   скрыта %s у %s (скрыл %s, %s): %s' % (r['inn'], a.get('username'), r.get('username'),
                                                     str(r.get('created_at') or '')[:16], str(r.get('reason') or '')[:80]))
    pole = ['inn', 'predpriyatie', 'region', 'strana', 'pometka_ocheredi'] + [c for c in kol if c.startswith('bitrix')]
    vyhod = {}
    for i, c in komp.items():
        z = {p: c.get(p) for p in pole if p in c}
        a = nazn.get(i) or {}
        z.update({'username': a.get('username'), 'stupen': a.get('stupen_ocheredi'), 'score': a.get('assignment_score')})
        vyhod[i] = z
    io.open(os.path.join(DROP, 'fixS-razvedka-kompanii.json'), 'w', encoding='utf-8').write(
        json.dumps(vyhod, ensure_ascii=False))
    print('на дроп: fixS-razvedka-kompanii.json (%d)' % len(vyhod))


def proverka(ts, tk):
    import warnings
    warnings.filterwarnings('ignore')
    sys.path.insert(0, KOREN)
    import zapusk  # noqa: F401
    import logging
    logging.disable(logging.CRITICAL)
    for kk in ('CENTRO_SALES_DB', 'PARK_OCHERED_SALES_DB'):
        os.environ[kk] = ts
    for kk in ('CENTRIFUGAL_DB', 'CENTRO_DB', 'PARK_OCHERED_DB'):
        os.environ[kk] = tk
    from app.api import routes_centro_sales as rcs
    from app.services import centro_catalog as catalog
    from app.services import centro_sales as sales
    from app.obzvon import create_app
    from fastapi.testclient import TestClient
    import csv as _csv
    print('базы – копии:', str(catalog.db_path()) == tk and str(sales.sales_db_path()) == ts)
    vnutr = next(z for z in vars(create_app()).values() if hasattr(z, 'routes') and hasattr(z, 'dependency_overrides'))
    ADMIN = {'id': 0, 'username': 'meyer_admin', 'role': 'admin', 'is_active': 1}
    kto = {'u': ADMIN}
    vnutr.dependency_overrides[rcs.current_user] = lambda: kto['u']
    rx_row = re.compile(r'<tr data-href="[^"]*centro\?inn=(\d+)[^"]*">')
    b = sqlite3.connect(ts)
    b.row_factory = sqlite3.Row
    kat = sqlite3.connect(tk)
    kat.row_factory = sqlite3.Row
    with TestClient(vnutr) as kl:
        for n_p, p in enumerate(['meyer4', 'meyer1'], 1):
            PROD = {'id': n_p, 'username': p, 'role': 'sales', 'is_active': 1}
            kto['u'] = PROD
            spisok = []
            for st in (1, 2, 3):
                o = kl.get(PUT + '/centro', params={'size': 100, 'page': st})
                spisok += rx_row.findall(o.text)
            kto['u'] = ADMIN
            o = kl.get(PUT + '/centro/vygruzka.csv', params={'assigned_user': p})
            csv_inn = [r[2] for r in list(_csv.reader(io.StringIO(o.content.decode('utf-8-sig')), delimiter=';'))[1:] if len(r) > 5]
            o2 = kl.get(PUT + '/centro', params={'assigned_user': p, 'size': 100, 'page': 1})
            kto['u'] = PROD
            o3 = kl.get(PUT + '/centro/vygruzka.csv')
            csv_prod = [r[2] for r in list(_csv.reader(io.StringIO(o3.content.decode('utf-8-sig')), delimiter=';'))[1:] if len(r) > 5] if o3.status_code == 200 else None
            nazn = [r[0] for r in b.execute('SELECT inn FROM company_assignment WHERE username=?', (p,))]
            print('%s: назначено %d, список менеджера %d (уник. %d), CSV директора %d, CSV менеджера %s' % (
                p, len(nazn), len(spisok), len(set(spisok)), len(csv_inn), (len(csv_prod) if csv_prod is not None else o3.status_code)))
            lishnie = (set(csv_inn) - set(spisok)) | (set(nazn) - set(spisok))
            for i in sorted(lishnie):
                c = kat.execute('SELECT inn, predpriyatie, pometka_ocheredi FROM company WHERE inn=?', (i,)).fetchone()
                a = b.execute('SELECT * FROM company_assignment WHERE inn=?', (i,)).fetchone()
                stt = [dict(r) for r in b.execute('SELECT * FROM company_state WHERE inn=?', (i,))]
                skr = [dict(r) for r in b.execute("SELECT * FROM hidden_item WHERE inn=?", (i,))]
                print('   нет в списке: %s «%s» в CSV=%s, назначение=%s, state=%s, hidden=%s' % (
                    i, (c['predpriyatie'] if c else '?'), i in csv_inn, dict(a) if a else None,
                    [{kk: v for kk, v in x.items() if kk in ('username', 'call_status', 'call_result', 'updated_at', 'next_contact_at')} for x in stt],
                    [{kk: v for kk, v in x.items() if kk in ('kind', 'value', 'username', 'reason', 'created_at')} for x in skr]))
                o4 = kl.get(PUT + '/centro', params={'inn': i})
                print('     карточка менеджеру: %s; в тексте «скрыта»: %s' % (o4.status_code, 'скрыта' in o4.text))
                # где она в списке директора
                kto['u'] = ADMIN
                for st in (1, 2, 3):
                    o5 = kl.get(PUT + '/centro', params={'assigned_user': p, 'size': 100, 'page': st})
                    if ('centro?inn=%s' % i) in o5.text:
                        print('     в списке директора по %s: стр. %d' % (p, st))
                kto['u'] = PROD


if __name__ == '__main__' and '--proverka' in sys.argv:
    i = sys.argv.index('--proverka')
    proverka(sys.argv[i + 1], sys.argv[i + 2])
else:
    razvedka()
    papka = os.path.join(KOREN, '_bekap', 'fixS-razvedka-' + time.strftime('%Y%m%d-%H%M%S'))
    os.makedirs(papka, exist_ok=True)
    ts, tk = os.path.join(papka, 'test_sales.db'), os.path.join(papka, 'test_kat.db')
    kopiya(SALES, ts)
    kopiya(KAT, tk)
    r = subprocess.run([VENV, os.path.abspath(__file__), '--proverka', ts, tk], capture_output=True,
                       timeout=900, cwd=KOREN, env=dict(os.environ, PYTHONIOENCODING='utf-8'))
    print(r.stdout.decode('utf-8', 'replace')[-3500:])
    if r.returncode:
        print('stderr:', r.stderr.decode('utf-8', 'replace')[-1500:])
    for t in (ts, tk):
        try:
            os.remove(t)
        except OSError:
            pass
