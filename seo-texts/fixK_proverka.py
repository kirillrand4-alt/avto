# -*- coding: utf-8 -*-
r"""fixK: итоговая проверка заливки MEYER-7 – только чтение, на ВРЕМЕННЫХ копиях баз (TestClient, без пароля).

    python3 zapusk_na_servere.py fixK_proverka.py --chast osnova      # счёт, регионы, холдинги, сделки, таблица качества
    python3 zapusk_na_servere.py fixK_proverka.py --chast kartochki   # 200 карточек новых: админ и свой продавец, чужой – нет
    python3 zapusk_na_servere.py fixK_proverka.py --chast filtry      # числа фильтров = строки (админ и 9 продавцов)

Результат – на дроп fixK-itog-<часть>-<время>.txt (и хвост в ответе).
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
PLAN = os.path.join(DROP, 'fixK-plan.json')
PUT = '/obzvon-meyer'
STARYE = ['meyer1', 'meyer2', 'meyer3', 'meyer4']
NOVYE_PR = ['meyer5', 'meyer6', 'meyer7', 'meyer8', 'meyer9']
PRODAVCY = STARYE + NOVYE_PR
FIO = {'meyer1': 'Пяткова', 'meyer2': 'Ерохин', 'meyer3': 'Беляев', 'meyer4': 'Волков', 'meyer5': 'Козлов',
       'meyer6': 'Тюнин', 'meyer7': 'Иванов', 'meyer8': 'Кузнецова', 'meyer9': 'Кузьмин'}
VREMYA = time.strftime('%Y%m%d-%H%M%S')
CHAST = sys.argv[sys.argv.index('--chast') + 1] if '--chast' in sys.argv else 'osnova'


def kopiya(src, dst):
    a = sqlite3.connect('file:%s?mode=ro' % src, uri=True)
    b = sqlite3.connect(dst)
    a.backup(b)
    b.close()
    a.close()


if '--vnutri' not in sys.argv:
    papka = os.path.join(KOREN, '_bekap', 'fixK-itog-' + VREMYA)
    os.makedirs(papka, exist_ok=True)
    ts, tk = os.path.join(papka, 'test_sales.db'), os.path.join(papka, 'test_kat.db')
    kopiya(SALES, ts)
    kopiya(KAT, tk)
    r = subprocess.run([VENV, os.path.abspath(__file__), '--vnutri', ts, tk, '--chast', CHAST], capture_output=True, timeout=1600,
                       cwd=KOREN, env=dict(os.environ, PYTHONIOENCODING='utf-8'))
    vyvod = r.stdout.decode('utf-8', 'replace') + r.stderr.decode('utf-8', 'replace')[-3000:]
    io.open(os.path.join(DROP, 'fixK-itog-%s-%s.txt' % (CHAST, VREMYA)), 'w', encoding='utf-8').write(vyvod)
    for t in (ts, tk):
        try:
            os.remove(t)
        except OSError:
            pass
    sys.stdout.write(vyvod[-5800:])
    raise SystemExit(r.returncode)

import html as H  # noqa: E402
import logging  # noqa: E402
import warnings  # noqa: E402
warnings.filterwarnings('ignore')
i_ = sys.argv.index('--vnutri')
TS, TK = sys.argv[i_ + 1], sys.argv[i_ + 2]
sys.path.insert(0, KOREN)
import zapusk  # noqa: E402,F401
logging.disable(logging.CRITICAL)
for kk in ('CENTRO_SALES_DB', 'PARK_OCHERED_SALES_DB'):
    os.environ[kk] = TS
for kk in ('CENTRIFUGAL_DB', 'CENTRO_DB', 'PARK_OCHERED_DB'):
    os.environ[kk] = TK
from app.api import routes_centro_sales as rcs  # noqa: E402
from app.services import centro_catalog as cat  # noqa: E402
from app.services import centro_sales as sales  # noqa: E402
from app.obzvon import create_app  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

plan = json.load(io.open(PLAN, encoding='utf-8'))
plohih = [0]


def ok(u, t):
    if not u:
        plohih[0] += 1
    print('   %s %s' % ('ОК ' if u else 'ПЛОХО', t))
    sys.stdout.flush()


ok(str(cat.db_path()) == TK and str(sales.sales_db_path()) == TS, 'базы – временные копии')
k = sqlite3.connect(TK)
k.row_factory = sqlite3.Row
s = sqlite3.connect(TS)
vlad = dict(s.execute('SELECT inn, username FROM company_assignment').fetchall())
kat = {r['inn']: dict(r) for r in k.execute('SELECT * FROM company')}
vse = set(kat)
novye = sorted(plan['prodavcy'])
sch = collections.Counter(vlad[i] for i in vse if i in vlad)
vnutr = next(z for z in vars(create_app()).values() if hasattr(z, 'routes') and hasattr(z, 'dependency_overrides'))
USERS = {'meyer_admin': {'id': 0, 'username': 'meyer_admin', 'role': 'admin', 'is_active': 1}}
for n_, p in enumerate(PRODAVCY, 1):
    USERS[p] = {'id': n_, 'username': p, 'role': 'sales', 'is_active': 1}
kto = {'u': USERS['meyer_admin']}
vnutr.dependency_overrides[rcs.current_user] = lambda: kto['u']


def total(t):
    m = re.search(r'<b class="total-count">(\d+) компаний</b>', t)
    return int(m.group(1)) if m else -1


def E2_modul():
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    for imya in ('3s_fixK_ball', '3s_fixF2_ball'):
        try:
            return __import__(imya)
        except ImportError:
            continue
    return None


if CHAST == 'osnova':
    ok(set(vlad) == vse and all(sch[p] == 270 for p in STARYE) and all(sch[p] == 120 for p in NOVYE_PR),
       'назначения = каталог (%d компаний); у продавцов: %s' % (len(vse), {FIO[p]: sch[p] for p in PRODAVCY}))
    sch_n = collections.Counter(vlad.get(i) for i in novye)
    ok(all(sch_n[p] == 120 for p in PRODAVCY) and all(vlad.get(i) == p for i, p in plan['prodavcy'].items()),
       'новых База 7 по 120 и по плану: %s' % {FIO[p]: sch_n[p] for p in PRODAVCY})
    for reg, kto_ in plan['dom'].items():
        c = collections.Counter(vlad.get(i) for i in vse if kat[i]['region'] == reg)
        ok(set(c) <= set(kto_), 'домашний регион «%s» (%d): %s – только %s' % (reg, sum(c.values()), {FIO[p]: n for p, n in c.items()},
                                                                         ', '.join(FIO[p] for p in kto_)))
    akt = set(plan.get('aktivnye_meyer_inn') or [])
    ok(not (set(novye) & akt), 'новых с активной сделкой Meyer (ИНН, ИНН в тексте сделки, точное название): %d' % len(set(novye) & akt))
    staryh_akt = sorted((vse - set(novye)) & akt)
    print('   (справочно) прежних компаний панели с ИНН в активных сделках Meyer: %d %s' % (len(staryh_akt), staryh_akt[:9]))
    razorv = []
    for g in {r[0] for r in k.execute("SELECT DISTINCT gruppa FROM holding_chlen WHERE gruppa NOT LIKE 'snyato%'")}:
        chl = [r[0] for r in k.execute('SELECT inn FROM holding_chlen WHERE gruppa=?', (g,)) if r[0] in vse]
        if len({vlad.get(i) for i in chl}) > 1:
            razorv.append((g, chl))
    for u, e in plan['edinicy'].items():
        chl = [i for i in e['novye'] + e['panel'] if i in vse]
        if len({vlad.get(i) for i in chl}) > 1:
            razorv.append((u, chl))
    ok(not razorv, 'холдинги (holding_chlen) и группы новых (общий сайт/номер/холдинг, связи с панелью) – у одного продавца: %d групп%s' % (
        len({r[0] for r in k.execute("SELECT DISTINCT gruppa FROM holding_chlen WHERE gruppa NOT LIKE 'snyato%'")}),
        ('; разорваны %s' % razorv[:4]) if razorv else ''))
    E2 = E2_modul()
    dannye = {}
    for inn in novye:
        dannye[inn] = E2.razbor_kompanii(kat[inn], cat.contacts(inn), cat, sales)
    score = dict(s.execute('SELECT inn, assignment_score FROM company_assignment').fetchall())
    stup = dict(s.execute('SELECT inn, stupen_ocheredi FROM company_assignment').fetchall())
    rash = [i for i in novye if abs(float(score[i]) - dannye[i]['score']) > 0.05 or int(stup[i]) != dannye[i]['tier']]
    ok(not rash, 'балл очереди и ступень новых = формула fixF2_ball: расхождений %d %s' % (len(rash), rash[:4]))

    def med(v):
        v = sorted(x for x in v if x)
        return (v[len(v) // 2] if len(v) % 2 else (v[len(v) // 2 - 1] + v[len(v) // 2]) / 2) if v else 0
    stroki = ['%-30s %s %s' % ('новые 120 (База 7)', ' '.join('%9s' % FIO[p][:9] for p in PRODAVCY), 'разница')]
    po = {p: [i for i in novye if vlad[i] == p] for p in PRODAVCY}

    def stroka(nazv, v, fmt='%9d'):
        stroki.append('%-30s %s %7s' % (nazv[:30], ' '.join(fmt % x for x in v), (fmt % (max(v) - min(v))).strip()))
    for t_, nazv in ((4, 'ЛПР ФИО+мобильный (800)'), (3, 'ЛПР мобильный (600)'), (2, 'ЛПР рабочий (400)'), (1, 'без ЛПР (200)')):
        stroka(nazv, [sum(1 for i in po[p] if dannye[i]['tier'] == t_) for p in PRODAVCY])
    stroka('ЛПР с мобильным (800+600)', [sum(1 for i in po[p] if dannye[i]['tier'] in (3, 4)) for p in PRODAVCY])
    stroka('ЛПР с ФИО', [sum(1 for i in po[p] if dannye[i]['lpr_fio']) for p in PRODAVCY])
    stroka('тех. ЛПР', [sum(1 for i in po[p] if dannye[i]['tech']) for p in PRODAVCY])
    eda = {r['inn']: r for r in plan['kompanii']}
    stroka('Беларусь', [sum(1 for i in po[p] if len(i) == 9) for p in PRODAVCY])
    stroka('медиана выручки РФ, млн', [med([dannye[i]['vyr'] for i in po[p] if len(i) != 9]) / 1e6 for p in PRODAVCY], '%9.0f')
    stroka('средний балл очереди', [sum(dannye[i]['score'] for i in po[p]) / len(po[p]) for p in PRODAVCY], '%9.1f')
    for reg in plan['dom']:
        stroka('регион ' + reg[:22], [sum(1 for i in po[p] if kat[i]['region'] == reg) for p in PRODAVCY])
    stroka('есть в Битриксе', [sum(1 for i in po[p] if kat[i].get('bitrix_kc')) for p in PRODAVCY])
    print('\n'.join(stroki))
    with TestClient(vnutr) as kl:
        def get(u, kak='meyer_admin', **kw):
            kto['u'] = USERS[kak]
            return kl.get(PUT + u, follow_redirects=False, **kw)
        for nazv, u in (('главная', '/centro'), ('статистика', '/centro/stats'), ('CSV', '/centro/vygruzka.csv')):
            o = get(u)
            ok(o.status_code == 200, 'админ, %s: %s' % (nazv, o.status_code))
        ok(total(get('/centro').text) == len(vse), 'админ, «Вся очередь»: %d' % total(get('/centro').text))
        for p in PRODAVCY:
            o = get('/centro', p)
            ok(o.status_code == 200 and total(o.text) == sch[p], '%s: «Вся очередь» %d' % (FIO[p], total(o.text)))
            o = get('/centro/stats', p)
            ok(o.status_code == 403, '%s: статистика закрыта (%s)' % (FIO[p], o.status_code))
        n_b = total(get('/centro', params={'baza': 'База 7'}).text)
        ok(n_b == len(novye), 'фильтр «Источник базы: База 7»: %d' % n_b)

elif CHAST == 'kartochki':
    rx_dd = re.compile(r'<dt>([^<]+)</dt><dd>(.*?)</dd>', re.S)
    vybor = novye[::max(1, len(novye) // 200)][:200]
    est_p = lambda c: any(c.get(x) for x in ('pasport_syrye', 'pasport_kachestvo', 'pasport_oborudovanie', 'pasport_upakovka',  # noqa: E731
                                             'pasport_eksport', 'pasport_masshtab'))
    sch_ = collections.Counter()
    with TestClient(vnutr) as kl:
        def get(u, kak='meyer_admin', **kw):
            kto['u'] = USERS[kak]
            return kl.get(PUT + u, follow_redirects=False, **kw)
        for inn in vybor:
            c = kat[inn]
            p = vlad[inn]
            for kak in ('meyer_admin', p):
                o = get('/centro', kak, params={'inn': inn})
                t = o.text
                dd = {a.strip(): re.sub(r'\s+', ' ', H.unescape(re.sub(r'<[^>]+>', ' ', b))).strip() for a, b in rx_dd.findall(t)}
                plohoe = []
                if o.status_code != 200:
                    plohoe.append('код %s' % o.status_code)
                if H.escape(c['predpriyatie'], quote=False) not in t and c['predpriyatie'] not in H.unescape(t):
                    plohoe.append('нет названия')
                if 'contact-card' not in t:
                    plohoe.append('нет контактов')
                if est_p(c) != ('Паспорт компании' in t):
                    plohoe.append('паспорт: в данных %s, в карточке %s' % (est_p(c), 'Паспорт компании' in t))
                if c.get('reviziya_profil') and 'Ревизия сборки:' not in t:
                    plohoe.append('нет ревизии')
                if 'База 7' not in t:
                    plohoe.append('нет метки «База 7»')
                rekv = ('Статус ЕГРЮЛ',) + (('Адрес', 'Директор') if len(inn) != 9 else ())
                pusto = [x for x in rekv if dd.get(x, '–') in ('', '–')]
                if pusto:
                    plohoe.append('пустые реквизиты %s' % pusto)
                if c.get('vyruchka_rub') and dd.get('Выручка', '–') in ('', '–'):
                    plohoe.append('выручка не показана')
                sch_['карточек'] += 1
                sch_['с паспортом'] += int('Паспорт компании' in t)
                sch_['ок'] += int(not plohoe)
                if plohoe:
                    ok(False, 'карточка %s (%s) у %s: %s' % (inn, c['predpriyatie'][:30], kak, '; '.join(plohoe)))
            drugoy = next(x for x in PRODAVCY if x != p)
            o = get('/centro', drugoy, params={'inn': inn})
            vidit = o.status_code == 200 and 'contact-card' in o.text and c['predpriyatie'] in H.unescape(o.text)
            sch_['чужой не видит'] += int(not vidit)
            if vidit:
                ok(False, 'чужой продавец %s видит карточку %s' % (drugoy, inn))
        ok(sch_['ок'] == sch_['карточек'] and sch_['чужой не видит'] == len(vybor),
           'карточки новых: %d компаний × (админ + свой продавец) = %d, без замечаний %d, с паспортом %d; чужой не видит %d из %d' % (
               len(vybor), sch_['карточек'], sch_['ок'], sch_['с паспортом'], sch_['чужой не видит'], len(vybor)))

elif CHAST == 'filtry':
    def filtry(t):
        res = []
        for m in re.finditer(r'<select name="([a-z_]+)"[^>]*>(.*?)</select>', t, re.S):
            for o in re.finditer(r'<option value="([^"]*)"[^>]*>([^<]*)</option>', m.group(2)):
                v, lab = H.unescape(o.group(1)), H.unescape(o.group(2)).strip()
                mm = re.search(r'[·–]\s*(\d+)\s*$', lab)
                if v and mm:
                    res.append((m.group(1), v, int(mm.group(1)), lab))
        for m in re.finditer(r'<input type="checkbox" name="([a-z_]+)" value="1"[^>]*>([^<]*)</label>', t):
            lab = H.unescape(m.group(2)).strip()
            mm = re.search(r'·\s*(\d+)\s*$', lab)
            if mm:
                res.append((m.group(1), '1', int(mm.group(1)), lab))
        return list(dict.fromkeys(res))
    kakie = [x for x in sys.argv if x.startswith('meyer')] or ['meyer_admin'] + PRODAVCY
    with TestClient(vnutr) as kl:
        def get(u, kak='meyer_admin', **kw):
            kto['u'] = USERS[kak]
            return kl.get(PUT + u, follow_redirects=False, **kw)
        for kak in kakie:
            t = get('/centro', kak).text
            plohie = []
            fl = filtry(t)
            for imya, v, n, lab in fl:
                if imya in ('sort', 'call_status', 'assigned_user'):
                    continue
                nn = total(get('/centro', kak, params={imya: v}).text)
                if nn != n:
                    plohie.append((imya, v, n, nn))
            ok(not plohie, '%s: пунктов фильтров с числом %d, каждый находит показанное число%s' % (
                kak, len(fl), ('; расхождения: %s' % plohie[:8]) if plohie else ''))
print('ПЛОХИХ ПРОВЕРОК: %d' % plohih[0])
raise SystemExit(1 if plohih[0] else 0)
