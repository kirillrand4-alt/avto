# -*- coding: utf-8 -*-
"""fixC: замер «до/после» – только чтение (рендер карточек TestClient и счётчики фильтров).

    python3 zapusk_na_servere.py fixC_zamer.py <метка: do|posle>

Перезапускает себя под venv. Карточки примеров рендерятся как у админа (кто наверху, роль,
ФИО, вид номера, что в «Остальных»), счётчики – из того же _source_companies(), что и
фильтры главной («Телефон с ролью», «Есть тех. ЛПР», «ЛПР с мобильным», «ЛПР с ФИО»),
по базам. Итог – fixC-zamer-<метка>.json на дропе. Ничего не пишет ни в код, ни в базы.
"""
import html as _h
import io
import json
import os
import re
import subprocess
import sys
import time

VENV = r'C:\seostat\.venv\Scripts\python.exe'
KOREN = r'C:\centro2'
DROP = r'C:\seostat\drop\drop-storage'
PUT = '/obzvon-meyer'
PRIMERY = ['6111008006', '2222826352', '5214007700', '5020087834', '7107109860', '6123008018',
           '3444015371', '3254002818', '5029139935', '2344007569', '7720619975', '9718181790',
           '5957004185', '7720631299', '1660183627', '5809003195', '5809005604', '1829013726',
           '3525279862', '7609002208', '6213014182', '1901124236', '3111005730', '7802590893',
           '5406851234', '6451402458', '7722686649', '4804006480', '5052022420', '4703149259',
           '1016043315', '0202008355', '7128012316', '1435071552', '7203319557', '5636002901',
           '4238013194', '6451402458', '6382000106', '1675003926']

if '--vnutri' not in sys.argv:
    metka = sys.argv[1] if len(sys.argv) > 1 else 'do'
    sreda = dict(os.environ, PYTHONIOENCODING='utf-8')
    r = subprocess.run([VENV, os.path.abspath(__file__), '--vnutri', metka], capture_output=True,
                       timeout=1500, cwd=KOREN, env=sreda)
    sys.stdout.write(r.stdout.decode('utf-8', 'replace')[-5500:])
    if r.returncode:
        sys.stdout.write('\n--- stderr ---\n' + r.stderr.decode('utf-8', 'replace')[-2500:])
    raise SystemExit(r.returncode)

metka = sys.argv[sys.argv.index('--vnutri') + 1]
sys.path.insert(0, KOREN)
import zapusk  # noqa: F401,E402
import logging  # noqa: E402
import warnings  # noqa: E402
warnings.filterwarnings('ignore')
logging.disable(logging.CRITICAL)
from app.api import routes_centro_sales as rcs  # noqa: E402
from app.services import centro_sales as sales  # noqa: E402
from app.obzvon import create_app  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


def tekst(s):
    return re.sub(r'\s+', ' ', _h.unescape(re.sub(r'<[^>]+>', ' ', s or ''))).strip()


def razobrat_kartochku(t):
    i = t.find('contacts-section')
    j = t.find('</section>', i)
    sek = t[i:j] if i >= 0 else ''
    k = sek.find('<details class="fold"')
    out = {}
    for chast, kus in (('verh', sek[:k] if k >= 0 else sek), ('ostalnye', sek[k:] if k >= 0 else '')):
        sp = []
        for a in re.findall(r'<article class="contact-card[^"]*".*?</article>', kus, re.S):
            nomer = tekst((re.search(r'class="contact-value"[^>]*>(.*?)</', a, re.S) or [None, ''])[1])
            metki = [tekst(x) for x in re.findall(r'<span class="tag[^"]*"[^>]*>(.*?)</span>', a, re.S)]
            chel = re.search(r'<div class="contact-person">\s*<b>(.*?)</b>\s*(?:<span>(.*?)</span>)?', a, re.S)
            chuzh = re.search(r'<div class="chuzhoy-metka">(.*?)</div>', a, re.S)
            sp.append({'nomer': nomer, 'metki': metki, 'fio': tekst(chel.group(1)) if chel else '',
                       'dolzh': tekst(chel.group(2)) if chel and chel.group(2) else '',
                       'chuzhoy': tekst(chuzh.group(1)) if chuzh else '',
                       'href': (re.search(r'href="(tel:[^"]*)"', a) or [None, ''])[1]})
        out[chast] = sp
    return out


vnutr = next(z for z in vars(create_app()).values() if hasattr(z, 'routes') and hasattr(z, 'dependency_overrides'))
vnutr.dependency_overrides[rcs.current_user] = lambda: {'id': 0, 'username': 'meyer_admin', 'role': 'admin', 'is_active': 1}
companies, _, _ = rcs._source_companies()
po_inn = {c['inn']: c for c in companies}
schet = {}


def baz(c):
    return [b.strip() for b in str(c.get('bazy') or '').split('|') if b.strip()] + ['все']


for c in companies:
    for b in baz(c):
        z = schet.setdefault(b, {'kompaniy': 0, 'telefon_s_rolyu': 0, 'teh_lpr': 0, 'lpr_mobilnyy': 0,
                                 'lpr_s_fio': 0, 'zakupki': 0})
        z['kompaniy'] += 1
        z['telefon_s_rolyu'] += int(bool(c.get('has_role_phone')))
        z['teh_lpr'] += int(bool(c.get('has_tech')))
        z['lpr_mobilnyy'] += int(bool(c.get('lpr_mobilnyy')))
        z['lpr_s_fio'] += int(bool(c.get('lpr_s_fio')))
        z['zakupki'] += int(bool(c.get('has_purchaser')))
sost = {}
try:
    with sales.connect() as s:
        for r in s.execute('select inn, call_result from company_state'):
            if r[1]:
                sost[str(r[0])] = r[1]
except Exception:  # noqa: BLE001
    pass
kartochki, plohih, kody = {}, 0, []
filtry = {}
with TestClient(vnutr) as kl:
    for f in ('has_role_phone', 'has_tech', 'lpr_mobilnyy', 'lpr_fio'):
        t = kl.get(PUT + '/centro', params={f: '1'}).text
        m = re.search(r'<b class="total-count">(\d+) компаний</b>', t)
        filtry[f] = int(m.group(1)) if m else -1
    for inn in dict.fromkeys(PRIMERY):
        if inn not in po_inn:
            kartochki[inn] = {'net_v_kataloge': 1}
            continue
        p = {'inn': inn}
        if sost.get(inn) in ('v_rabote', 'ne_ponravilas', 'dubl'):
            p['call_status'] = sost[inn]
        o = kl.get(PUT + '/centro', params=p)
        if o.status_code != 200:
            plohih += 1
        k = razobrat_kartochku(o.text)
        k['kod'] = o.status_code
        c = po_inn[inn]
        k['kompaniya'] = {x: c.get(x) for x in ('predpriyatie', 'bazy', 'lpr_kratko', 'lpr_roli', 'lpr_mobilnyy',
                                               'lpr_s_fio', 'has_tech', 'has_purchaser', 'has_role_phone',
                                               'n_phones', 'n_tech', 'n_purchaser')}
        kartochki[inn] = k
    for u in ({'id': 0, 'username': 'meyer_admin', 'role': 'admin', 'is_active': 1},
              {'id': 1, 'username': 'meyer2', 'role': 'sales', 'is_active': 1}):
        vnutr.dependency_overrides[rcs.current_user] = lambda u=u: u
        for put in ('/centro', '/centro/stats'):
            o = kl.get(PUT + put)
            kody.append('%s %s %s' % (u['username'], put, o.status_code))
            if o.status_code != 200 and not (u['role'] == 'sales' and put.endswith('stats') and o.status_code in (303, 403)):
                plohih += 1
itog = {'metka': metka, 'vremya': time.strftime('%Y-%m-%d %H:%M:%S'), 'schetchiki_po_bazam': schet,
        'filtry_glavnoy_admin': filtry, 'kartochki': kartochki}
put_ = os.path.join(DROP, 'fixC-zamer-%s.json' % metka)
io.open(put_, 'w', encoding='utf-8').write(json.dumps(itog, ensure_ascii=False, indent=1))
print('замер «%s» -> %s' % (metka, put_))
print('фильтры главной (админ, вся очередь):', filtry)
for b in sorted(schet):
    print('  %-8s %s' % (b, schet[b]))
for inn in list(dict.fromkeys(PRIMERY))[:12]:
    k = kartochki.get(inn) or {}
    v = k.get('verh') or []
    print('  %s наверху %d, в остальных %d; первый: %s' % (inn, len(v), len(k.get('ostalnye') or []),
          ('%s | %s | %s' % (v[0]['nomer'], v[0]['fio'], v[0]['dolzh'])) if v else '–'))
print('ответы страниц:', '; '.join(kody))
print('ПЛОХИХ ОТВЕТОВ: %d' % plohih)
