# -*- coding: utf-8 -*-
r"""fixI: правило владельца 13.10 «у кого какой город – другим этот город не отдавать (область/край)».

В базе продаж (одна транзакция, журнал «было/стало» – на дроп):
  1. users.gorod для meyer1–meyer4: Барнаул / Краснодар / Краснодар / Барнаул (у meyer5–9 уже записан – не трогается);
  2. перестановки по плану fixI_plan.py: 6 алтайских от Ерохина/Беляева – Пятковой/Волкову, взамен столько же
     компаний из не домашних регионов – Ерохину/Беляеву (колонка vladelec_do_fixI). Перед записью база перечитывается:
     компании с действиями продавцов не переезжают (иначе остановка без изменений).
Каталог не меняется, код панели не меняется, перезапуска нет.
Проверка на копиях: по 150 у meyer1–4 и 0 у meyer5–9, алтайские только у Пятковой/Волкова, краснодарские только у
Ерохина/Беляева (поровну), воронежских 0, города записаны, холдинги и пары с общими номерами – у одного продавца,
главные страницы 200, карточки переехавших – у нового продавца есть, у прежнего нет, числа фильтров = строки.

    python3 zapusk_na_servere.py fixI_zamena.py [--suhoy]
    python3 zapusk_na_servere.py fixI_zamena.py --tolko-proverka
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
PLAN = os.path.join(DROP, 'fixI-plan.json')
PUT = '/obzvon-meyer'
PRODAVCY = ['meyer1', 'meyer2', 'meyer3', 'meyer4']
NOVYE_PRODAVCY = ['meyer5', 'meyer6', 'meyer7', 'meyer8', 'meyer9']
DEYSTVIYA = ('company_state', 'company_comment', 'zvonok_sobytie', 'activity_log', 'hidden_item')
GOROD = {'meyer1': 'Барнаул', 'meyer2': 'Краснодар', 'meyer3': 'Краснодар', 'meyer4': 'Барнаул'}
DOM = {'Алтайский край': ('meyer1', 'meyer4'), 'Краснодарский край': ('meyer2', 'meyer3'), 'Воронежская область': ()}
FIO = {'meyer1': 'Пяткова', 'meyer2': 'Ерохин', 'meyer3': 'Беляев', 'meyer4': 'Волков'}
VREMYA = time.strftime('%Y%m%d-%H%M%S')

if '--vnutri' not in sys.argv and '--proverka' not in sys.argv:
    r = subprocess.run([VENV, os.path.abspath(__file__), '--vnutri'] + sys.argv[1:], capture_output=True,
                       timeout=1650, cwd=KOREN, env=dict(os.environ, PYTHONIOENCODING='utf-8'))
    sys.stdout.write(r.stdout.decode('utf-8', 'replace')[-5900:])
    if r.returncode:
        sys.stdout.write('\n--- stderr ---\n' + r.stderr.decode('utf-8', 'replace')[-2500:])
    raise SystemExit(r.returncode)


def kopiya(src, dst):
    a = sqlite3.connect('file:%s?mode=ro' % src, uri=True)
    b = sqlite3.connect(dst)
    a.backup(b)
    b.close()
    a.close()


def zakrep(s, inny):
    out = {}
    inny = list(inny)
    if not inny:
        return out
    for t in DEYSTVIYA:
        try:
            n = s.execute('SELECT inn, COUNT(*) FROM %s WHERE inn IN (%s) GROUP BY inn' % (t, ','.join('?' * len(inny))),
                          inny).fetchall()
        except sqlite3.OperationalError:
            continue
        for inn, c in n:
            out.setdefault(inn, {})[t] = c
    return out


def rabota(KAT, SALES, plan, metka=''):
    from app.services import centro_sales as sales
    zh = {'vremya': VREMYA, 'suhoy': bool(metka), 'gorod': [], 'peremeshcheniya': []}
    s = sqlite3.connect(SALES, timeout=30)
    s.row_factory = sqlite3.Row
    s.execute('PRAGMA busy_timeout=30000')
    k = sqlite3.connect('file:%s?mode=ro' % KAT, uri=True)
    region = dict(k.execute('SELECT inn, region FROM company').fetchall())
    k.close()
    for _ in range(20):
        try:
            s.execute('BEGIN IMMEDIATE')
            break
        except sqlite3.OperationalError:
            time.sleep(3)
    else:
        raise SystemExit('база продаж занята')
    try:
        # ---------- сверка (внутри транзакции – база перечитана под записью)
        vlad = dict(s.execute('SELECT inn, username FROM company_assignment').fetchall())
        users = {r['username']: dict(r) for r in s.execute('SELECT id, username, role, is_active, gorod FROM users')}
        osh = []
        nety = [p for p in PRODAVCY if p not in users]
        if nety:
            osh.append('нет пользователей %s' % nety)
        per = plan['peremeshcheniya']
        for m in per:
            if vlad.get(m['inn']) != m['ot']:
                osh.append('%s: сейчас у %s, план переносит от %s' % (m['inn'], vlad.get(m['inn']), m['ot']))
        dz = zakrep(s, [m['inn'] for m in per])
        if dz:
            osh.append('ПО ПЕРЕЕЗЖАЮЩИМ ЕСТЬ ДЕЙСТВИЯ ПРОДАВЦОВ – не переношу: %s' % dz)
        n_dz = sum(len(zakrep(s, list(vlad)[i:i + 400])) for i in range(0, len(vlad), 400))
        sch0 = collections.Counter(vlad.values())
        if any(sch0[p] != plan['cel'][p] for p in PRODAVCY) or any(sch0[p] for p in NOVYE_PRODAVCY):
            osh.append('распределение сейчас не по плану: %s' % dict(sch0))
        if set(vlad) != set(region):
            osh.append('назначения не совпадают с каталогом')
        if osh:
            raise RuntimeError('ОСТАНОВКА:\n  ' + '\n  '.join(osh))
        print('сверка: перечитано %d назначений; компаний с действиями продавцов во всей базе: %d, среди переезжающих (%d): 0'
              % (len(vlad), n_dz, len(per)))
        # ---------- города продавцов
        for p, g in GOROD.items():
            bylo = users[p].get('gorod')
            if bylo != g:
                s.execute('UPDATE users SET gorod=? WHERE username=?', (g, p))
                zh['gorod'].append({'username': p, 'bylo': bylo, 'stalo': g})
        print('города: %s' % ('; '.join('%s %s -> %s' % (x['username'], x['bylo'], x['stalo']) for x in zh['gorod']) or 'уже записаны'))
        # ---------- перестановки
        kol = {r[1] for r in s.execute('PRAGMA table_info(company_assignment)')}
        if 'vladelec_do_fixI' not in kol:
            s.execute('ALTER TABLE company_assignment ADD COLUMN vladelec_do_fixI TEXT')
        seychas = sales.utcnow()
        for m in per:
            bylo = dict(s.execute('SELECT * FROM company_assignment WHERE inn=?', (m['inn'],)).fetchone())
            cur = s.execute('UPDATE company_assignment SET username=?, assigned_at=?, assigned_by=?, '
                            'vladelec_do_fixI=COALESCE(vladelec_do_fixI, ?) WHERE inn=? AND username=?',
                            (m['komu'], seychas, ('fixI 13.10: ' + m['prichina'])[:200], m['ot'], m['inn'], m['ot']))
            if cur.rowcount != 1:
                raise RuntimeError('перестановка не записалась: %s' % m['inn'])
            zh['peremeshcheniya'].append({'inn': m['inn'], 'ot': m['ot'], 'komu': m['komu'], 'bylo': bylo})
        vlad = dict(s.execute('SELECT inn, username FROM company_assignment').fetchall())
        sch = collections.Counter(vlad.values())
        if any(sch[p] != plan['cel'][p] for p in PRODAVCY) or any(sch[p] for p in NOVYE_PRODAVCY):
            raise RuntimeError('после перестановок не по плану: %s' % dict(sch))
        chuzhie = [(i, region[i], vlad[i]) for i in vlad if region.get(i) in DOM and vlad[i] not in DOM[region[i]]]
        if chuzhie:
            raise RuntimeError('после перестановок компании не у своего города: %s' % chuzhie)
        s.commit()
    except BaseException:
        s.rollback()
        raise
    finally:
        s.close()
    pot = collections.Counter((FIO[m['ot']], FIO[m['komu']]) for m in plan['peremeshcheniya'])
    print('перестановок %d: %s; итог %s' % (len(plan['peremeshcheniya']), dict(pot), dict(sch)))
    put = os.path.join(DROP, 'fixI-zhurnal-%s%s.json' % (VREMYA, metka))
    io.open(put, 'w', encoding='utf-8').write(json.dumps(zh, ensure_ascii=False, indent=1, default=str))
    print('журнал: %s' % put)
    return zh


# ====================================================================== ПРОВЕРКА (venv, копии баз)
def proverka(test_sales, test_kat):
    import html as H
    import warnings
    warnings.filterwarnings('ignore')
    sys.path.insert(0, KOREN)
    import zapusk  # noqa: F401
    import logging
    logging.disable(logging.CRITICAL)
    for kk in ('CENTRO_SALES_DB', 'PARK_OCHERED_SALES_DB'):
        os.environ[kk] = test_sales
    for kk in ('CENTRIFUGAL_DB', 'CENTRO_DB', 'PARK_OCHERED_DB'):
        os.environ[kk] = test_kat
    from app.api import routes_centro_sales as rcs
    from app.services import centro_catalog as cat
    from app.services import centro_sales as sales
    from app.obzvon import create_app
    from fastapi.testclient import TestClient
    plan = json.load(io.open(PLAN, encoding='utf-8'))
    plohih = [0]

    def ok(u, t):
        if not u:
            plohih[0] += 1
        print('   %s %s' % ('ОК ' if u else 'ПЛОХО', t))
        sys.stdout.flush()
    ok(str(cat.db_path()) == test_kat and str(sales.sales_db_path()) == test_sales, 'базы – временные копии')
    k = sqlite3.connect(test_kat)
    s = sqlite3.connect(test_sales)
    s.row_factory = sqlite3.Row
    vlad = dict(s.execute('SELECT inn, username FROM company_assignment').fetchall())
    region = dict(k.execute('SELECT inn, region FROM company').fetchall())
    naim = dict(k.execute('SELECT inn, predpriyatie FROM company').fetchall())
    sch = collections.Counter(vlad.values())
    ok(all(sch[p] == plan['cel'][p] for p in PRODAVCY) and set(vlad) == set(region),
       'у meyer1–4 по плану %s: %s; назначения = каталог (%d): %s' % (
           plan['cel'], {p: sch[p] for p in PRODAVCY}, len(region), set(vlad) == set(region)))
    ok(not any(sch[p] for p in NOVYE_PRODAVCY), 'у новых meyer5–9 компаний: %s' % {p: sch[p] for p in NOVYE_PRODAVCY})
    goroda = {r['username']: r['gorod'] for r in s.execute('SELECT username, gorod FROM users')}
    ok(all(goroda.get(p) == g for p, g in GOROD.items()), 'города в users: %s' % {p: goroda.get(p) for p in PRODAVCY + NOVYE_PRODAVCY})
    for reg, kto in DOM.items():
        inn = [i for i in region if region[i] == reg]
        c = collections.Counter(vlad.get(i) for i in inn)
        ok(set(c) <= set(kto), '%s (%d): %s – только %s' % (reg, len(inn), {FIO.get(p, p): n for p, n in c.items()},
                                                          ', '.join(FIO[p] for p in kto) or 'никому из четырёх'))
    krd = collections.Counter(vlad.get(i) for i in region if region[i] == 'Краснодарский край')
    ok(max(krd.values()) - min(krd.values()) <= 1, 'краснодарские у Ерохина и Беляева поровну: %s' % dict(krd))
    ok(all(vlad.get(m['inn']) == m['komu'] for m in plan['peremeshcheniya']), 'перестановок по плану: %d' % len(plan['peremeshcheniya']))
    # холдинги и пары с общими номерами
    razorv = []
    for g in {r[0] for r in k.execute("SELECT DISTINCT gruppa FROM holding_chlen WHERE gruppa NOT LIKE 'snyato%'")}:
        chl = [r[0] for r in k.execute('SELECT inn FROM holding_chlen WHERE gruppa=?', (g,)) if r[0] in region]
        if len({vlad.get(i) for i in chl}) > 1:
            razorv.append((g, chl))
    try:
        hold = json.load(io.open(os.path.join(DROP, 'fixD-holdingi.json'), encoding='utf-8'))
        for pp in hold['obshchie_nomera_bez_svyazi']:
            chl = [i for i in pp['inns'] if i in region]
            if len({vlad.get(i) for i in chl}) > 1:
                razorv.append(('общий номер', chl))
        for g in set(hold['inn_gruppa'].values()):
            chl = [i for i, gg in hold['inn_gruppa'].items() if gg == g and i in region]
            if len({vlad.get(i) for i in chl}) > 1:
                razorv.append((g, chl))
    except (OSError, ValueError):
        pass
    ok(not razorv, 'каждая группа холдинга и пара с общими номерами – у одного продавца%s' % (
        (': разорваны %s' % razorv[:5]) if razorv else ''))
    # рендер
    vnutr = next(z for z in vars(create_app()).values() if hasattr(z, 'routes') and hasattr(z, 'dependency_overrides'))
    USERS = {'meyer_admin': {'id': 0, 'username': 'meyer_admin', 'role': 'admin', 'is_active': 1}}
    for n_, p in enumerate(PRODAVCY + NOVYE_PRODAVCY, 1):
        USERS[p] = {'id': n_, 'username': p, 'role': 'sales', 'is_active': 1}
    kto = {'u': USERS['meyer_admin']}
    vnutr.dependency_overrides[rcs.current_user] = lambda: kto['u']

    def total(t):
        m = re.search(r'<b class="total-count">(\d+) компаний</b>', t)
        return int(m.group(1)) if m else -1

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
    with TestClient(vnutr) as kl:
        def get(u, kak='meyer_admin', **kw):
            kto['u'] = USERS[kak]
            return kl.get(PUT + u, follow_redirects=False, **kw)
        for nazv, u in (('главная', '/centro'), ('статистика', '/centro/stats')):
            o = get(u)
            ok(o.status_code == 200, 'админ, %s: %s' % (nazv, o.status_code))
        ok(total(get('/centro').text) == len(region), 'админ, «Вся очередь»: %d' % total(get('/centro').text))
        for p in PRODAVCY:
            o = get('/centro', p)
            ok(o.status_code == 200 and total(o.text) == plan['cel'][p], '%s: главная %s, в очереди %d' % (p, o.status_code, total(o.text)))
        for p in NOVYE_PRODAVCY:
            o = get('/centro', p)
            ok(o.status_code == 200 and total(o.text) in (0, -1), '%s (новый): главная %s, в очереди %s' % (p, o.status_code, total(o.text)))
        n_nov = sum(1 for _ in s.execute('SELECT 1 FROM company_assignment WHERE username IN (%s)' % ','.join('?' * len(NOVYE_PRODAVCY)),
                                         NOVYE_PRODAVCY))
        ok(n_nov == 0, 'после открытия главной новыми продавцами назначений у них: %d' % n_nov)
        for m in plan['peremeshcheniya']:
            o1 = get('/centro', m['komu'], params={'inn': m['inn']})
            o2 = get('/centro', m['ot'], params={'inn': m['inn']})
            ok(o1.status_code == 200 and (o2.status_code != 200 or naim[m['inn']] not in o2.text),
               '%s (%s, %s): у %s карточка %s, у прежнего %s – %s' % (m['inn'], naim[m['inn']][:28], region[m['inn']][:18], FIO[m['komu']],
                                                                    o1.status_code, FIO[m['ot']], o2.status_code))
        for kak in ['meyer_admin'] + PRODAVCY:
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
    return plohih[0]


if '--proverka' in sys.argv:
    i = sys.argv.index('--proverka')
    raise SystemExit(1 if proverka(sys.argv[i + 1], sys.argv[i + 2]) else 0)


def zapustit_proverku(papka, metka=''):
    ts, tk = os.path.join(papka, 'test_sales.db'), os.path.join(papka, 'test_kat.db')
    kopiya(SALES if not metka else os.path.join(papka, 'suhoy_sales.db'), ts)
    kopiya(KAT, tk)
    r = subprocess.run([VENV, os.path.abspath(__file__), '--proverka', ts, tk], capture_output=True, timeout=1300, cwd=KOREN,
                       env=dict(os.environ, PYTHONIOENCODING='utf-8'))
    vyvod = r.stdout.decode('utf-8', 'replace') + r.stderr.decode('utf-8', 'replace')[-3000:]
    io.open(os.path.join(DROP, 'fixI-proverka%s-%s.txt' % (metka, time.strftime('%Y%m%d-%H%M%S'))), 'w', encoding='utf-8').write(vyvod)
    for t in (ts, tk):
        try:
            os.remove(t)
        except OSError:
            pass
    return vyvod


if '--vnutri' in sys.argv:
    sys.path.insert(0, KOREN)
    import zapusk  # noqa: F401  – .env в окружение
    import logging
    logging.disable(logging.CRITICAL)
    BEKAP = os.path.join(KOREN, '_bekap', 'fixI-' + VREMYA)
    os.makedirs(BEKAP, exist_ok=True)
    if '--tolko-proverka' in sys.argv:
        print(zapustit_proverku(BEKAP)[-5500:])
        raise SystemExit(0)
    plan = json.load(io.open(PLAN, encoding='utf-8'))
    if '--suhoy' in sys.argv:
        ts = os.path.join(BEKAP, 'suhoy_sales.db')
        kopiya(SALES, ts)
        for kk in ('CENTRO_SALES_DB', 'PARK_OCHERED_SALES_DB'):
            os.environ[kk] = ts
        rabota(KAT, ts, plan, '-suhoy')
        print('===== ПРОВЕРКА РЕПЕТИЦИИ (на копиях) =====')
        print(zapustit_proverku(BEKAP, '-suhoy')[-4000:])
        os.remove(ts)
        raise SystemExit(0)
    assert os.path.normcase(os.environ.get('CENTRO_SALES_DB', '')) == os.path.normcase(SALES)
    kopiya(SALES, os.path.join(BEKAP, 'centro_sales_meyer1.db'))
    print('копия базы продаж (НЕ для отката целиком): %s' % BEKAP)
    rabota(KAT, SALES, plan)
    print('===== ПРОВЕРКА (на копиях баз после записи) =====')
    print(zapustit_proverku(BEKAP)[-3500:])
