# -*- coding: utf-8 -*-
r"""fixJ: владелец 13.10 «нынешние усиль, потом пересчитай, чтобы равное было».

  1. каталог (одна транзакция, журнал «было/стало» – на дроп): новые номера и люди из базы соседней сессии MEYER-7
     у общих с ней компаний панели; ФИО/должность, дописанные к нашим номерам без подписи; новые почты в
     company.pochta; флаги ЛПР, lpr_kratko и search_blob затронутых компаний. Перед записью каждый номер снова
     сверяется с живой базой: если такой номер у компании уже появился (например, его добавил продавец) – пропуск;
     дописывание – только если наш номер всё ещё без ФИО/должности, как в плане;
  2. продажи: перестановки для ровного качества (колонка vladelec_do_fixJ); база перечитывается, компании с
     действиями продавцов не переезжают (иначе остановка без изменений перестановок).
Код панели не меняется, перезапуска нет. Балл очереди – отдельным прогоном fixF2_ball.py --tolko-ball.

План (номера телефонов – только в нём) собирает локально fixJ_plan.py -> дроп fixJ-plan.json.

    python3 zapusk_na_servere.py fixJ_zamena.py [--suhoy]
    python3 zapusk_na_servere.py fixJ_zamena.py --tolko-proverka
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
PLAN = os.path.join(DROP, 'fixJ-plan.json')
PUT = '/obzvon-meyer'
PRODAVCY = ['meyer1', 'meyer2', 'meyer3', 'meyer4']
NOVYE_PRODAVCY = ['meyer5', 'meyer6', 'meyer7', 'meyer8', 'meyer9']
DEYSTVIYA = ('company_state', 'company_comment', 'zvonok_sobytie', 'activity_log', 'hidden_item')
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


def podkl(put):
    k = sqlite3.connect(put, timeout=30)
    k.row_factory = sqlite3.Row
    k.execute('PRAGMA busy_timeout=30000')
    return k


def nachat(k):
    for _ in range(20):
        try:
            k.execute('BEGIN IMMEDIATE')
            return
        except sqlite3.OperationalError:
            time.sleep(3)
    raise SystemExit('база занята')


def zakrep(s, inny):
    out = {}
    inny = list(inny)
    for i in range(0, len(inny), 400):
        kus = inny[i:i + 400]
        for t in DEYSTVIYA:
            try:
                n = s.execute('SELECT inn, COUNT(*) FROM %s WHERE inn IN (%s) GROUP BY inn' % (t, ','.join('?' * len(kus))),
                              kus).fetchall()
            except sqlite3.OperationalError:
                continue
            for inn, c in n:
                out.setdefault(inn, {})[t] = c
    return out


# ====================================================================== флаги ЛПР (копия fixF2_dannye / fixH_zamena)
def pokaz(cat, v):
    osn, dob = cat._razdelit_dobavochnyy(v)
    d = re.sub(r'\D', '', osn)
    if len(d) == 11 and d[0] == '7':
        osn = '+7 %s %s-%s-%s' % (d[1:4], d[4:7], d[7:9], d[9:])
    return osn + (' доб. ' + dob if dob else '')


def flagi(cat, items):
    tel = [x for x in items if x['kind'] == 'phone']
    lpr = [x for x in tel if x['lpr']]
    sprosit = [x for x in items if x['kind'] == 'sprosit']
    roli = list(dict.fromkeys(x['rol_vid'] for x in lpr))
    fio_lpr = {cat._kl_fio(x['person']) for x in lpr if x['person']}
    mob = [x for x in lpr if x['vid_nomera'] == 'мобильный']
    fio_mob = [x for x in mob if x['person']]
    if lpr:
        l0 = (fio_mob or mob or lpr)[0]
        kr = ' · '.join(v for v in (l0['person'], l0['position'] or l0['rol_vid'], pokaz(cat, l0['value'])) if v)
        if len(lpr) > 1:
            kr += ' (+ ещё %d)' % (len(lpr) - 1)
    elif sprosit:
        s0 = sprosit[0]
        kr = '%s · %s (без номера – спросить у приёмной)' % (s0['person'], s0['position'] or s0['rol_vid'])
    else:
        put_ = [x for x in tel if x['has_role']]
        if put_:
            p0 = put_[0]
            kr = ('ЛПР не найден, через приёмную: %s' if p0['rol_vid'] in ('приёмная', 'общий номер')
                  else 'ЛПР не найден, номер с сайта: %s') % pokaz(cat, p0['value'])
            n_mob = sum(1 for x in tel if x['vid_nomera'] == 'мобильный')
            if n_mob:
                kr += ' (мобильных без ЛПР: %d)' % n_mob
        else:
            kr = 'ЛПР не найден' + (', номера только неличные: %d' % len(tel) if tel else ', номеров нет')
    return {'has_tech': int(any(x['is_tech'] for x in lpr)), 'n_tech': sum(1 for x in lpr if x['is_tech']),
            'has_purchaser': int(any(x['is_purchaser'] for x in lpr)), 'n_purchaser': sum(1 for x in lpr if x['is_purchaser']),
            'lpr_mobilnyy': int(bool(mob)), 'lpr_s_fio': len(fio_lpr), 'lpr_roli': ', '.join(roli), 'lpr_kratko': kr,
            'n_phones': len(tel), 'has_phone': int(bool(tel))}



def blob(cat, c, items, kratko):
    return ' '.join(str(v) for v in (
        c['inn'], c['predpriyatie'], c['region'], c['okvedy_vse'], c['segment'], c['opisanie'], c.get('produkciya'),
        c.get('holding'), c['sayt'], kratko, c.get('adres'), c.get('direktor'),
        ' '.join('%s %s %s %s' % (x.get('person') or '', x.get('position') or '', x.get('rol_vid') or '',
                                  cat._phone_key(x.get('value'))) for x in items if x['kind'] in ('phone', 'sprosit'))) if v).lower()


# ====================================================================== ОСНОВНАЯ РАБОТА
def rabota(KAT, SALES, plan, metka=''):
    from app.services import centro_catalog as cat
    zh = {'vremya': VREMYA, 'suhoy': bool(metka), 'kontakty': [], 'lyudi': [], 'dopisano': [], 'pochta': [], 'flagi': [],
          'propushcheno': [], 'peremeshcheniya': []}

    def kl(v):
        osn, dob = cat._razdelit_dobavochnyy(v)
        return re.sub(r'\D', '', osn)[-10:], (dob or '')
    k = podkl(KAT)
    s = podkl(SALES)
    # ---------- 1. сверка продаж до любой записи
    vlad = dict(s.execute('SELECT inn, username FROM company_assignment').fetchall())
    per = plan['peremeshcheniya']
    osh = []
    for m in per:
        if vlad.get(m['inn']) != m['ot']:
            osh.append('%s: сейчас у %s, план переносит от %s' % (m['inn'], vlad.get(m['inn']), m['ot']))
    dz_vse = zakrep(s, list(vlad))
    dz = {i: v for i, v in dz_vse.items() if i in {m['inn'] for m in per}}
    if dz:
        osh.append('ПО ПЕРЕЕЗЖАЮЩИМ ЕСТЬ ДЕЙСТВИЯ ПРОДАВЦОВ – не переношу: %s' % dz)
    sch0 = collections.Counter(vlad.values())
    if any(sch0[p] != plan['cel'][p] for p in PRODAVCY) or any(sch0[p] for p in NOVYE_PRODAVCY):
        osh.append('распределение сейчас не по плану: %s' % dict(sch0))
    if osh:
        print('ОСТАНОВКА, ничего не изменено:\n  ' + '\n  '.join(osh))
        raise SystemExit(4)
    print('сверка: назначений %d; компаний с действиями продавцов во всей базе: %d (%s); среди переезжающих (%d): 0' % (
        len(vlad), len(dz_vse), sorted(dz_vse)[:10], len(per)))

    # ---------- 2. каталог: номера, люди, дописывание, почты, флаги
    nachat(k)
    try:
        kol_k = {r[1] for r in k.execute('PRAGMA table_info(contact)')}
        kol_p = {r[1] for r in k.execute('PRAGMA table_info(person)')}
        est = collections.defaultdict(set)
        for r in k.execute("SELECT inn, value FROM contact WHERE kind='phone'"):
            est[r['inn']].add(kl(r['value']))
        for x in plan['kontakty']:
            kk = kl(x['value'])
            if kk in est[x['inn']]:
                zh['propushcheno'].append({'inn': x['inn'], 'value': x['value'], 'pochemu': 'номер у компании уже есть'})
                continue
            est[x['inn']].add(kk)
            rr = {c: v for c, v in x.items() if c in kol_k}
            cur = k.execute('INSERT INTO contact (%s) VALUES (%s)' % (','.join(rr), ','.join('?' * len(rr))), list(rr.values()))
            zh['kontakty'].append(cur.lastrowid)
        est_p = {(r['inn'], cat._kl_fio(r['person']), kl(r['phone'] or '')[0]) for r in k.execute('SELECT inn, person, phone FROM person')
                 if r['person']}
        for x in plan['lyudi']:
            kk = (x['inn'], cat._kl_fio(x['person']), kl(x['phone'] or '')[0])
            if kk in est_p:
                zh['propushcheno'].append({'inn': x['inn'], 'person': x['person'], 'pochemu': 'человек уже есть'})
                continue
            est_p.add(kk)
            rr = {c: v for c, v in x.items() if c in kol_p}
            cur = k.execute('INSERT INTO person (%s) VALUES (%s)' % (','.join(rr), ','.join('?' * len(rr))), list(rr.values()))
            zh['lyudi'].append(cur.lastrowid)
        for x in plan['dopisano']:
            r = k.execute('SELECT inn, value, person, position, source FROM contact WHERE id=?', (x['id'],)).fetchone()
            if not r or r['inn'] != x['inn'] or kl(r['value']) != kl(x['value']) or \
                    (r['person'], r['position'], r['source']) != (x['bylo']['person'], x['bylo']['position'], x['bylo']['source']):
                zh['propushcheno'].append({'inn': x['inn'], 'id': x['id'], 'pochemu': 'номер изменился после снимка – не дописываю'})
                continue
            k.execute('UPDATE contact SET person=?, position=?, source=? WHERE id=?',
                      (x['stalo']['person'], x['stalo']['position'], x['stalo']['source'], x['id']))
            zh['dopisano'].append({'id': x['id'], 'inn': x['inn'], 'bylo': x['bylo'], 'stalo': x['stalo']})
        for inn, v in plan['pochta'].items():
            r = k.execute('SELECT pochta FROM company WHERE inn=?', (inn,)).fetchone()
            if r is None:
                continue
            seychas = r['pochta'] or ''
            if seychas == (v['bylo'] or ''):
                stalo = v['stalo']
            else:                                   # почту меняли после снимка – дописываю только новые адреса
                imeyutsya = {e.lower() for e in re.findall(r'[\w.+-]+@[\w-]+(?:\.[\w-]+)+', seychas)}
                dob = [chast for chast in re.split(r', (?=[\w.+-]+@)', v['stalo'][len(v['bylo'] or ''):].lstrip(', '))
                       if chast and chast.split(' ', 1)[0].lower() not in imeyutsya]
                stalo = ', '.join(x_ for x_ in [seychas] + dob if x_)[:4000]
            if stalo != seychas:
                k.execute('UPDATE company SET pochta=? WHERE inn=?', (stalo, inn))
                zh['pochta'].append({'inn': inn, 'bylo': seychas or None, 'stalo': stalo})
        zatronuty = sorted({x['inn'] for x in plan['kontakty']} | {x['inn'] for x in plan['lyudi']} |
                           {x['inn'] for x in plan['dopisano']})
        k.commit()
    except BaseException:
        k.rollback()
        raise
    nachat(k)
    try:
        for inn in zatronuty:
            c = dict(k.execute('SELECT * FROM company WHERE inn=?', (inn,)).fetchone())
            items = cat.contacts(inn)
            nov = flagi(cat, items)
            nov['search_blob'] = blob(cat, c, items, nov['lpr_kratko'])
            izm = {p: v for p, v in nov.items() if c.get(p) != v}
            if izm:
                k.execute('UPDATE company SET %s WHERE inn=?' % ', '.join('"%s"=?' % p for p in izm), list(izm.values()) + [inn])
                zh['flagi'].append({'inn': inn, 'bylo': {p: c.get(p) for p in izm if p != 'search_blob'},
                                    'stalo': {p: v for p, v in izm.items() if p != 'search_blob'}})
        k.commit()
    except BaseException:
        k.rollback()
        raise
    print('каталог: номеров добавлено %d, людей %d, дописано ФИО/должность %d, почт обновлено у %d компаний, флаги у %d; '
          'пропущено %d %s' % (len(zh['kontakty']), len(zh['lyudi']), len(zh['dopisano']), len(zh['pochta']), len(zh['flagi']),
                               len(zh['propushcheno']), collections.Counter(x['pochemu'] for x in zh['propushcheno'])))
    k.close()

    # ---------- 3. продажи: перестановки
    nachat(s)
    try:
        vlad = dict(s.execute('SELECT inn, username FROM company_assignment').fetchall())
        dz = zakrep(s, [m['inn'] for m in per])
        if dz or any(vlad.get(m['inn']) != m['ot'] for m in per):
            raise RuntimeError('за время записи каталога изменились назначения или появились действия: %s' % dz)
        kol = {r[1] for r in s.execute('PRAGMA table_info(company_assignment)')}
        if 'vladelec_do_fixJ' not in kol:
            s.execute('ALTER TABLE company_assignment ADD COLUMN vladelec_do_fixJ TEXT')
        from app.services import centro_sales as sales
        seychas = sales.utcnow()
        for m in per:
            cur = s.execute('UPDATE company_assignment SET username=?, assigned_at=?, assigned_by=?, '
                            'vladelec_do_fixJ=COALESCE(vladelec_do_fixJ, ?) WHERE inn=? AND username=?',
                            (m['komu'], seychas, ('fixJ 13.10: ' + m['prichina'])[:200], m['ot'], m['inn'], m['ot']))
            if cur.rowcount != 1:
                raise RuntimeError('перестановка не записалась: %s' % m['inn'])
            zh['peremeshcheniya'].append(m)
        vlad = dict(s.execute('SELECT inn, username FROM company_assignment').fetchall())
        sch = collections.Counter(vlad.values())
        if any(sch[p] != plan['cel'][p] for p in PRODAVCY) or any(sch[p] for p in NOVYE_PRODAVCY):
            raise RuntimeError('после перестановок не по плану: %s' % dict(sch))
        kk_ = sqlite3.connect('file:%s?mode=ro' % KAT, uri=True)
        region = dict(kk_.execute('SELECT inn, region FROM company').fetchall())
        kk_.close()
        chuzhie = [(i, region[i], vlad[i]) for i in vlad if region.get(i) in DOM and vlad[i] not in DOM[region[i]]]
        if chuzhie:
            raise RuntimeError('после перестановок компании не у своего города: %s' % chuzhie)
        s.commit()
    except BaseException:
        s.rollback()
        print('ПЕРЕСТАНОВКИ НЕ ЗАПИСАНЫ (каталог уже усилен – это не мешает работе; перестановки можно повторить)')
        raise
    finally:
        s.close()
    pot = collections.Counter((FIO[m['ot']], FIO[m['komu']]) for m in per)
    print('продажи: перестановок %d %s; итог %s' % (len(per), dict(pot), {p: sch[p] for p in PRODAVCY}))
    put = os.path.join(DROP, 'fixJ-zhurnal-%s%s.json' % (VREMYA, metka))
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
    k.row_factory = sqlite3.Row
    s = sqlite3.connect(test_sales)
    vlad = dict(s.execute('SELECT inn, username FROM company_assignment').fetchall())
    region = dict(k.execute('SELECT inn, region FROM company').fetchall())
    naim = dict(k.execute('SELECT inn, predpriyatie FROM company').fetchall())
    sch = collections.Counter(vlad.values())
    ok(all(sch[p] == plan['cel'][p] for p in PRODAVCY) and set(vlad) == set(region),
       'у meyer1–4 по плану %s: %s; назначения = каталог (%d)' % (plan['cel'], {p: sch[p] for p in PRODAVCY}, len(region)))
    ok(not any(sch[p] for p in NOVYE_PRODAVCY), 'у новых meyer5–9 компаний: %s' % {p: sch[p] for p in NOVYE_PRODAVCY})
    for reg, kto in DOM.items():
        c = collections.Counter(vlad.get(i) for i in region if region[i] == reg)
        ok(set(c) <= set(kto), '%s: %s – только %s' % (reg, {FIO.get(p, p): n for p, n in c.items()},
                                                    ', '.join(FIO[p] for p in kto) or 'никому из четырёх'))
    krd = collections.Counter(vlad.get(i) for i in region if region[i] == 'Краснодарский край')
    ok(max(krd.values()) - min(krd.values()) <= 1, 'краснодарские у Ерохина и Беляева поровну: %s' % dict(krd))
    ok(all(vlad.get(m['inn']) == m['komu'] for m in plan['peremeshcheniya']), 'перестановок по плану: %d' % len(plan['peremeshcheniya']))
    n_m7 = k.execute("SELECT COUNT(*) FROM contact WHERE source LIKE 'MEYER-7 13.10:%'").fetchone()[0]
    n_m7c = k.execute("SELECT COUNT(*) FROM contact WHERE source LIKE 'MEYER-7 13.10:%' AND COALESCE(chuzhoy_istochnik,'')<>''").fetchone()[0]
    n_dop = k.execute("SELECT COUNT(*) FROM contact WHERE source LIKE '%дописаны из MEYER-7 13.10%'").fetchone()[0]
    n_p = k.execute("SELECT COUNT(*) FROM person WHERE source LIKE 'MEYER-7 13.10:%'").fetchone()[0]
    ok(n_m7 > 0 and n_m7 <= len(plan['kontakty']) and n_p > 0,
       'в каталоге номеров из MEYER-7: %d (в плане %d), с меткой чужого/группы %d; дописано к нашим %d; людей из MEYER-7 %d' % (
           n_m7, len(plan['kontakty']), n_m7c, n_dop, n_p))
    # ступени по формуле = план (у поднявшихся)
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    E2 = None
    for imya in ('3s_fixF2_ball', 'fixF2_ball'):
        try:
            E2 = __import__(imya)
            break
        except ImportError:
            continue
    if E2:
        raz = []
        for i, st in plan['stupeni'].items():
            c = dict(k.execute('SELECT * FROM company WHERE inn=?', (i,)).fetchone())
            d = E2.razbor_kompanii(c, cat.contacts(i), cat, sales)
            if d['tier'] != st['tier']:
                raz.append((i, st['tier'], d['tier']))
        ok(not raz, 'ступени всех 600 по формуле = план (поднялись %d)%s' % (len(plan['podnyalis']), ('; расходятся: %s' % raz[:8]) if raz else ''))
    # холдинги и пары с общими номерами (в т. ч. новые из MEYER-7)
    razorv = []
    for g in {r[0] for r in k.execute("SELECT DISTINCT gruppa FROM holding_chlen WHERE gruppa NOT LIKE 'snyato%'")}:
        chl = [r[0] for r in k.execute('SELECT inn FROM holding_chlen WHERE gruppa=?', (g,)) if r[0] in region]
        if len({vlad.get(i) for i in chl}) > 1:
            razorv.append((g, chl))
    pary = list(plan['obshchie_novye'])
    try:
        hold = json.load(io.open(os.path.join(DROP, 'fixD-holdingi.json'), encoding='utf-8'))
        pary += hold['obshchie_nomera_bez_svyazi']
        for g in set(hold['inn_gruppa'].values()):
            chl = [i for i, gg in hold['inn_gruppa'].items() if gg == g and i in region]
            if len({vlad.get(i) for i in chl}) > 1:
                razorv.append((g, chl))
    except (OSError, ValueError):
        pass
    for pp in pary:
        chl = [i for i in pp['inns'] if i in region]
        if len({vlad.get(i) for i in chl}) > 1:
            razorv.append(('общий номер', chl))
    ok(not razorv, 'каждая группа холдинга и пара с общими номерами (в т. ч. %d новых из MEYER-7) – у одного продавца%s' % (
        len(plan['obshchie_novye']), (': разорваны %s' % razorv[:5]) if razorv else ''))
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
        for p in PRODAVCY:
            o = get('/centro', p)
            ok(o.status_code == 200 and total(o.text) == plan['cel'][p], '%s: главная %s, в очереди %d' % (p, o.status_code, total(o.text)))
        # карточки: все поднявшиеся + все с новыми номерами (админ), свой продавец – у поднявшихся и переехавших
        s_novymi = sorted({x['inn'] for x in plan['kontakty']})
        plohie = []
        for inn in s_novymi:
            o = get('/centro', params={'inn': inn})
            if o.status_code != 200 or 'MEYER-7 13.10' not in o.text:
                plohie.append((inn, o.status_code))
        ok(not plohie, 'карточки с новыми номерами (%d): 200 и источник «MEYER-7 13.10» виден%s' % (
            len(s_novymi), ('; плохо: %s' % plohie[:8]) if plohie else ''))
        for x in plan['podnyalis']:
            inn = x['inn']
            p = vlad[inn]
            o = get('/centro', p, params={'inn': inn})
            t = o.text
            i0 = t.find('contacts-section')
            sek = t[i0:t.find('</section>', i0)] if i0 >= 0 else ''
            tsifry = re.sub(r'\D', '', sek)
            lpr = [y for y in cat.contacts(inn) if y['kind'] == 'phone' and y['lpr']]
            vidny = [y for y in lpr if re.sub(r'\D', '', y['value'].split('доб')[0])[-10:] in tsifry]
            ok(o.status_code == 200 and vidny, 'поднялась %s (%s) %d→%d, у %s: %s; ЛПР в карточке: %s' % (
                inn, naim[inn][:26], x['bylo'], x['stalo'], FIO[p], o.status_code,
                ', '.join(dict.fromkeys('%s%s' % (y['rol_vid'], ' (MEYER-7)' if 'MEYER-7' in y['source'] else '') for y in vidny))[:90]))
        for m in plan['peremeshcheniya']:
            o1 = get('/centro', m['komu'], params={'inn': m['inn']})
            o2 = get('/centro', m['ot'], params={'inn': m['inn']})
            ok(o1.status_code == 200 and (o2.status_code != 200 or naim[m['inn']] not in o2.text),
               'переехала %s (%s): у %s %s, у прежнего %s – %s' % (m['inn'], naim[m['inn']][:26], FIO[m['komu']], o1.status_code,
                                                                  FIO[m['ot']], o2.status_code))
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


def zapustit_proverku(papka, sales_src=None, kat_src=None, metka=''):
    ts, tk = os.path.join(papka, 'test_sales.db'), os.path.join(papka, 'test_kat.db')
    kopiya(sales_src or SALES, ts)
    kopiya(kat_src or KAT, tk)
    r = subprocess.run([VENV, os.path.abspath(__file__), '--proverka', ts, tk], capture_output=True, timeout=1300, cwd=KOREN,
                       env=dict(os.environ, PYTHONIOENCODING='utf-8'))
    vyvod = r.stdout.decode('utf-8', 'replace') + r.stderr.decode('utf-8', 'replace')[-3000:]
    io.open(os.path.join(DROP, 'fixJ-proverka%s-%s.txt' % (metka, time.strftime('%Y%m%d-%H%M%S'))), 'w', encoding='utf-8').write(vyvod)
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
    BEKAP = os.path.join(KOREN, '_bekap', 'fixJ-' + VREMYA)
    os.makedirs(BEKAP, exist_ok=True)
    if '--tolko-proverka' in sys.argv:
        print(zapustit_proverku(BEKAP)[-5500:])
        raise SystemExit(0)
    plan = json.load(io.open(PLAN, encoding='utf-8'))
    if '--suhoy' in sys.argv:
        tk, ts = os.path.join(BEKAP, 'suhoy_kat.db'), os.path.join(BEKAP, 'suhoy_sales.db')
        kopiya(KAT, tk)
        kopiya(SALES, ts)
        for kk in ('CENTRIFUGAL_DB', 'CENTRO_DB', 'PARK_OCHERED_DB'):
            os.environ[kk] = tk
        for kk in ('CENTRO_SALES_DB', 'PARK_OCHERED_SALES_DB'):
            os.environ[kk] = ts
        rabota(tk, ts, plan, '-suhoy')
        print('===== ПРОВЕРКА РЕПЕТИЦИИ (на копиях) =====')
        print(zapustit_proverku(BEKAP, ts, tk, '-suhoy')[-4500:])
        for f in (tk, ts):
            try:
                os.remove(f)
            except OSError:
                pass
        raise SystemExit(0)
    assert os.path.normcase(os.environ.get('CENTRIFUGAL_DB', '')) == os.path.normcase(KAT)
    assert os.path.normcase(os.environ.get('CENTRO_SALES_DB', '')) == os.path.normcase(SALES)
    kopiya(KAT, os.path.join(BEKAP, 'meyer_baza1.db'))
    kopiya(SALES, os.path.join(BEKAP, 'centro_sales_meyer1.db'))
    print('копии баз (НЕ для отката целиком): %s' % BEKAP)
    rabota(KAT, SALES, plan)
    print('===== ПРОВЕРКА (на копиях баз после записи) =====')
    print(zapustit_proverku(BEKAP)[-3500:])
