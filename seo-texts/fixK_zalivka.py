# -*- coding: utf-8 -*-
r"""fixK: заливка базы MEYER-7 в панель Meyer – по 120 новых компаний каждому из meyer1–meyer9 (владелец 13.10).

План (номера телефонов – только в нём) собирает локально fixK_plan.py -> дроп fixK-plan.json.
Шаги (короткие транзакции, журнал «было/стало» – на дроп):
  1. сверка: новых ИНН нет ни в каталоге, ни в назначениях; у meyer1–4 сейчас по 150, у meyer5–9 – 0; продавцы
     компаний панели, к которым по плану пристёгнуты группы новых, не сменились;
  2. продажи: назначения новых (ДО вставки в каталог – иначе панель раздала бы их сама, assign_new); итог 270/120;
  3. каталог: новые колонки company (паспорт, сегмент сборки, ревизия, база обзвона и т. д.), компании, номера, люди,
     источники, строки холдингов (holding_chlen); import_info. Ошибка – откат каталога и удаление назначений Базы 7;
  4. флаги ЛПР, lpr_kratko, search_blob новых – по контактам карточки (живая функция contacts); балл очереди и ступень
     новых – формула fixF2_ball (razbor_kompanii).
Код панели не меняется, перезапуска нет. Проверка – отдельным процессом на копиях баз (--proverka).

    python3 zapusk_na_servere.py fixK_zalivka.py --suhoy        # репетиция на копиях боевых баз
    python3 zapusk_na_servere.py fixK_zalivka.py                # запись + проверка
    python3 zapusk_na_servere.py fixK_zalivka.py --tolko-proverka
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
SOURCE_VERSION = 'meyer-baza7-fixK'
DEYSTVIYA = ('company_state', 'company_comment', 'zvonok_sobytie', 'activity_log', 'hidden_item')
VREMYA = time.strftime('%Y%m%d-%H%M%S')

if '--vnutri' not in sys.argv and '--proverka' not in sys.argv:
    r = subprocess.run([VENV, os.path.abspath(__file__), '--vnutri'] + sys.argv[1:], capture_output=True,
                       timeout=1680, cwd=KOREN, env=dict(os.environ, PYTHONIOENCODING='utf-8'))
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


def kolonki(k, t):
    return [r[1] for r in k.execute('PRAGMA table_info(%s)' % t)]


def E2_modul():
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    for imya in ('3s_fixK_ball', '3s_fixF2_ball', 'fixF2_ball'):
        try:
            return __import__(imya)
        except ImportError:
            continue
    return None


def flagi(cat, items):        # = fixK_m7.flagi = fixH_zamena.flagi
    tel = [x for x in items if x['kind'] == 'phone']
    lpr = [x for x in tel if x['lpr']]
    sprosit = [x for x in items if x['kind'] == 'sprosit']
    roli = list(dict.fromkeys(x['rol_vid'] for x in lpr))
    fio_lpr = {cat._kl_fio(x['person']) for x in lpr if x['person']}
    mob = [x for x in lpr if x['vid_nomera'] == 'мобильный']
    fio_mob = [x for x in mob if x['person']]

    def pokaz(v):
        osn, dob = cat._razdelit_dobavochnyy(v)
        d = re.sub(r'\D', '', osn)
        if len(d) == 11 and d[0] == '7':
            osn = '+7 %s %s-%s-%s' % (d[1:4], d[4:7], d[7:9], d[9:])
        return osn + (' доб. ' + dob if dob else '')
    if lpr:
        l0 = (fio_mob or mob or lpr)[0]
        kr = ' · '.join(v for v in (l0['person'], l0['position'] or l0['rol_vid'], pokaz(l0['value'])) if v)
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
                  else 'ЛПР не найден, номер с сайта: %s') % pokaz(p0['value'])
            n_mob = sum(1 for x in tel if x['vid_nomera'] == 'мобильный')
            if n_mob:
                kr += ' (мобильных без ЛПР: %d)' % n_mob
        else:
            kr = 'ЛПР не найден' + (', номера только неличные: %d' % len(tel) if tel else ', номеров нет')
    return {'has_tech': int(any(x['is_tech'] for x in lpr)), 'n_tech': sum(1 for x in lpr if x['is_tech']),
            'has_purchaser': int(any(x['is_purchaser'] for x in lpr)), 'n_purchaser': sum(1 for x in lpr if x['is_purchaser']),
            'lpr_mobilnyy': int(bool(mob)), 'lpr_s_fio': len(fio_lpr), 'lpr_roli': ', '.join(roli), 'lpr_kratko': kr,
            'n_phones': len(tel), 'has_phone': int(bool(tel))}


# ====================================================================== ОСНОВНАЯ РАБОТА
def rabota(KAT, SALES, plan, suhoy_metka=''):
    from app.services import centro_catalog as cat
    from app.services import centro_sales as sales
    zh = {'vremya': VREMYA, 'suhoy': bool(suhoy_metka), 'naznacheniya': [], 'kolonki_dobavleny': [], 'vstavleno': {},
          'flagi': [], 'ball': [], 'oshibki': []}
    novye = {c['inn']: c for c in plan['kompanii']}
    prodavec = plan['prodavcy']
    k = podkl(KAT)
    s = podkl(SALES)
    # ---------- 1. сверка
    vlad = dict(s.execute('SELECT inn, username FROM company_assignment').fetchall())
    v_kat = {r[0] for r in k.execute('SELECT inn FROM company')}
    users = {r['username']: dict(r) for r in s.execute('SELECT username, role, is_active FROM users')}
    osh = []
    if set(novye) & v_kat:
        osh.append('новые уже в каталоге: %s' % sorted(set(novye) & v_kat)[:10])
    if set(novye) & set(vlad):
        osh.append('у новых уже есть назначения: %s' % sorted(set(novye) & set(vlad))[:10])
    sch = collections.Counter(vlad.values())
    if any(sch[p] != 150 for p in STARYE) or any(sch[p] for p in NOVYE_PR):
        osh.append('распределение сейчас не 150×4 и 0×5: %s' % dict(sch))
    for p in PRODAVCY:
        if p not in users or users[p]['role'] != 'sales' or not users[p]['is_active']:
            osh.append('продавца %s нет или не активен' % p)
    for u, e in plan['edinicy'].items():
        for j in e['panel']:
            if j not in vlad:
                osh.append('компании панели %s (группа новых %s) нет в назначениях' % (j, e['novye']))
    if set(prodavec) != set(novye) or collections.Counter(prodavec.values()) != collections.Counter({p: plan['nuzhno'] for p in PRODAVCY}):
        osh.append('в плане не по %d каждому' % plan['nuzhno'])
    if osh:
        print('ОСТАНОВКА, ничего не изменено:\n  ' + '\n  '.join(osh))
        raise SystemExit(4)
    print('сверка: новых %d, в каталоге сейчас %d, назначения %s' % (len(novye), len(v_kat), dict(sch)))

    # ---------- 2. продажи: назначения новых ДО каталога
    nachat(s)
    try:
        seychas = sales.utcnow()
        kol_a = set(kolonki(s, 'company_assignment'))
        for inn, p in sorted(prodavec.items()):
            st = plan['stupeni'][inn]
            c = novye[inn]
            a = {'inn': inn, 'username': p, 'assignment_score': st['score'], 'has_phone': int(c.get('has_phone') or 0),
                 'has_purchaser': int(c.get('has_purchaser') or 0), 'has_tech': int(c.get('has_tech') or 0), 'has_signal': 0,
                 'assigned_at': seychas, 'source_version': SOURCE_VERSION,
                 'assigned_by': 'База 7 (MEYER-7, поиск по России и Беларуси) 13.10 (fixK): по 120 каждому, холдинги и домашние регионы',
                 'stupen_ocheredi': st['tier']}
            a = {kk: v for kk, v in a.items() if kk in kol_a}
            s.execute('INSERT INTO company_assignment (%s) VALUES (%s)' % (','.join(a), ','.join('?' * len(a))), list(a.values()))
            zh['naznacheniya'].append(a)
        sch2 = collections.Counter(r[0] for r in s.execute('SELECT username FROM company_assignment'))
        if any(sch2[p] != 270 for p in STARYE) or any(sch2[p] != 120 for p in NOVYE_PR):
            raise RuntimeError('после назначений не 270/120: %s' % dict(sch2))
        s.commit()
    except BaseException:
        s.rollback()
        raise
    print('продажи: назначено %d; итог %s' % (len(zh['naznacheniya']), dict(sch2)))

    def ubrat_naznacheniya():
        nachat(s)
        n = s.execute('DELETE FROM company_assignment WHERE source_version=? AND inn IN (%s)' % ','.join('?' * len(novye)),
                      [SOURCE_VERSION] + list(novye)).rowcount
        s.commit()
        print('АВАРИЯ: назначения Базы 7 удалены (%d)' % n)

    # ---------- 3. каталог: колонки, компании, номера, люди, источники, холдинги
    try:
        kc = set(kolonki(k, 'company'))
        for c_, tip in plan['novye_kolonki']:
            if c_ not in kc:
                k.execute('ALTER TABLE company ADD COLUMN %s %s' % (c_, tip))
                zh['kolonki_dobavleny'].append(c_)
        k.commit()
        nachat(k)
        kc, kk_, kp = set(kolonki(k, 'company')), set(kolonki(k, 'contact')), set(kolonki(k, 'person'))
        net = sorted({x for c in novye.values() for x in c} - kc)
        if net:
            raise RuntimeError('в каталоге нет колонок company: %s' % net)
        zh['vstavleno'] = {'company': [], 'contact': [], 'person': [], 'company_source': [], 'holding_chlen': []}
        for inn, c in novye.items():
            k.execute('INSERT INTO company (%s) VALUES (%s)' % (','.join('"%s"' % x for x in c), ','.join('?' * len(c))), list(c.values()))
            zh['vstavleno']['company'].append(inn)
        for x in plan['kontakty']:
            r = {kk: v for kk, v in x.items() if kk in kk_}
            cur = k.execute('INSERT INTO contact (%s) VALUES (%s)' % (','.join(r), ','.join('?' * len(r))), list(r.values()))
            zh['vstavleno']['contact'].append(cur.lastrowid)
        for x in plan['lyudi']:
            r = {kk: v for kk, v in x.items() if kk in kp}
            cur = k.execute('INSERT INTO person (%s) VALUES (%s)' % (','.join(r), ','.join('?' * len(r))), list(r.values()))
            zh['vstavleno']['person'].append(cur.lastrowid)
        for x in plan['istochniki']:
            cur = k.execute('INSERT INTO company_source (inn, field_name, source, source_url) VALUES (?,?,?,?)',
                            (x['inn'], x['field_name'], x['source'], x['source_url']))
            zh['vstavleno']['company_source'].append(cur.lastrowid)
        kh = set(kolonki(k, 'holding_chlen'))
        for x in plan['holding_chlen']:
            r = {kk: v for kk, v in x.items() if kk in kh}
            k.execute('INSERT INTO holding_chlen (%s) VALUES (%s)' % (','.join(r), ','.join('?' * len(r))), list(r.values()))
            zh['vstavleno']['holding_chlen'].append([x['gruppa'], x['inn']])
        for kk, v in {'baza7_fajl': 'MEYER-7.xlsx (сборка соседней сессии 13.10)', 'baza7_zalito': time.strftime('%Y-%m-%d %H:%M'),
                      'baza7_kompaniy_novyh': str(len(novye)), 'baza7_kontaktov': str(len(plan['kontakty'])),
                      'fixK_zalivka': VREMYA, 'fixK_dobavleno': ','.join(sorted(novye))}.items():
            k.execute('INSERT OR REPLACE INTO import_info (key, value) VALUES (?,?)', (kk, v))
        n = k.execute('SELECT COUNT(*) FROM company').fetchone()[0]
        if n != len(v_kat) + len(novye):
            raise RuntimeError('в каталоге %d компаний (ждали %d)' % (n, len(v_kat) + len(novye)))
        k.commit()
    except BaseException:
        k.rollback()
        ubrat_naznacheniya()
        raise
    print('каталог: колонки добавлены %s; новых – компаний %d, номеров %d, людей %d, источников %d, строк холдингов %d' % (
        len(zh['kolonki_dobavleny']), len(zh['vstavleno']['company']), len(zh['vstavleno']['contact']),
        len(zh['vstavleno']['person']), len(zh['vstavleno']['company_source']), len(zh['vstavleno']['holding_chlen'])))

    # ---------- 4. флаги ЛПР, search_blob – по живым контактам карточки; балл очереди и ступень – формула fixF2_ball
    E2 = E2_modul()
    obnov = {}
    for inn in novye:
        c = dict(k.execute('SELECT * FROM company WHERE inn=?', (inn,)).fetchone())
        items = cat.contacts(inn)
        nov = flagi(cat, items)
        nov['search_blob'] = ' '.join(str(v) for v in (
            inn, c['predpriyatie'], c['region'], c.get('okvedy_vse'), c.get('segment'), c.get('segment_meyer7'), c.get('opisanie'),
            c.get('produkciya'), c.get('holding'), c.get('sayt'), nov['lpr_kratko'], c.get('adres'), c.get('direktor'),
            ' '.join('%s %s %s %s' % (x.get('person') or '', x.get('position') or '', x.get('rol_vid') or '',
                                      cat._phone_key(x.get('value'))) for x in items if x['kind'] in ('phone', 'sprosit'))) if v).lower()
        c2 = dict(c, **nov)
        st = None
        if E2:
            d = E2.razbor_kompanii(c2, items, cat, sales)
            st = {'score': d['score'], 'tier': d['tier']}
            nov['moy_prioritet'], nov['prioritet_pochemu'] = d['ball'], d['pochemu']
            if d['tier'] != plan['stupeni'][inn]['tier']:
                zh['oshibki'].append('%s: ступень на сервере %d, в плане %d' % (inn, d['tier'], plan['stupeni'][inn]['tier']))
        obnov[inn] = (c, nov, st)
    nachat(k)
    try:
        for inn, (c, nov, st) in obnov.items():
            izm = {p: v for p, v in nov.items() if c.get(p) != v}
            if izm:
                k.execute('UPDATE company SET %s WHERE inn=?' % ', '.join('"%s"=?' % p for p in izm), list(izm.values()) + [inn])
                zh['flagi'].append({'inn': inn, 'bylo': {p: c.get(p) for p in izm if p != 'search_blob'},
                                    'stalo': {p: v for p, v in izm.items() if p != 'search_blob'}})
        k.commit()
    except BaseException:
        k.rollback()
        raise
    nachat(s)
    try:
        for inn, (c, nov, st) in obnov.items():
            if st:
                s.execute('UPDATE company_assignment SET has_phone=?, has_purchaser=?, has_tech=?, assignment_score=?, stupen_ocheredi=? '
                          'WHERE inn=? AND source_version=?', (nov['has_phone'], nov['has_purchaser'], nov['has_tech'], st['score'],
                                                               st['tier'], inn, SOURCE_VERSION))
                zh['ball'].append({'inn': inn, 'score': st['score'], 'tier': st['tier']})
        s.commit()
    except BaseException:
        s.rollback()
        raise
    print('флаги: обновлены у %d; балл очереди по формуле: %s (%d); расхождений ступени с планом: %d %s' % (
        len(zh['flagi']), 'fixF2_ball' if E2 else 'НЕ НАЙДЕНА – балл плана', len(zh['ball']), len(zh['oshibki']), zh['oshibki'][:5]))
    k.close()
    s.close()
    put = os.path.join(DROP, 'fixK-zhurnal-%s%s.json' % (VREMYA, suhoy_metka))
    io.open(put, 'w', encoding='utf-8').write(json.dumps(zh, ensure_ascii=False, indent=0, default=str))
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
    vse = {r[0] for r in k.execute('SELECT inn FROM company')}
    region = dict(k.execute('SELECT inn, region FROM company').fetchall())
    novye = set(plan['prodavcy'])
    sch = collections.Counter(vlad[i] for i in vse if i in vlad)
    sch_n = collections.Counter(vlad[i] for i in novye if i in vlad)
    ok(set(vlad) == vse and all(sch[p] == 270 for p in STARYE) and all(sch[p] == 120 for p in NOVYE_PR),
       'назначения = каталог (%d); всего у продавцов %s' % (len(vse), dict(sorted(sch.items()))))
    ok(novye <= vse and all(sch_n[p] == 120 for p in PRODAVCY), 'новых по 120: %s' % dict(sorted(sch_n.items())))
    ok(all(vlad.get(i) == p for i, p in plan['prodavcy'].items()), 'новые – у продавцов по плану')
    for reg, kto in plan['dom'].items():
        c = collections.Counter(vlad.get(i) for i in vse if region[i] == reg)
        ok(set(c) <= set(kto), 'домашний регион %s (%d): %s – только %s' % (reg, sum(c.values()), dict(c), kto))
    # активные сделки Meyer (у самой компании) – 0 в рабочем каталоге
    akt = set(plan.get('aktivnye_meyer_inn') or [])
    ok(not (vse & akt), 'компаний с активной сделкой Meyer (ИНН сделки, ИНН в тексте, точное название) в каталоге: %d %s' % (
        len(vse & akt), sorted(vse & akt)[:5]))
    # холдинги и общие номера
    razorv = []
    for g in {r[0] for r in k.execute("SELECT DISTINCT gruppa FROM holding_chlen WHERE gruppa NOT LIKE 'snyato%'")}:
        chl = [r[0] for r in k.execute('SELECT inn FROM holding_chlen WHERE gruppa=?', (g,)) if r[0] in vse]
        if len({vlad.get(i) for i in chl}) > 1:
            razorv.append((g, chl))
    for u, e in plan['edinicy'].items():
        chl = [i for i in e['novye'] + e['panel'] if i in vse]
        if len({vlad.get(i) for i in chl}) > 1:
            razorv.append((u, chl, [vlad.get(i) for i in chl]))
    ok(not razorv, 'группы холдингов (каталог) и группы новых с общими номерами/сайтом – у одного продавца%s' % (
        (': разорваны %s' % razorv[:4]) if razorv else ''))
    # метка базы, паспорт, контакты
    n_b7 = k.execute("SELECT COUNT(*) FROM company WHERE bazy LIKE '%База 7%'").fetchone()[0]
    ok(n_b7 == len(novye), 'метка «База 7»: %d' % n_b7)
    n_k = k.execute('SELECT COUNT(*) FROM contact WHERE inn IN (%s)' % ','.join('?' * len(novye)), list(novye)).fetchone()[0]
    ok(n_k == len(plan['kontakty']), 'номеров новых в каталоге %d = план %d' % (n_k, len(plan['kontakty'])))
    # балл/ступень = формула
    E2 = E2_modul()
    score = dict(s.execute('SELECT inn, assignment_score FROM company_assignment').fetchall())
    stup = dict(s.execute('SELECT inn, stupen_ocheredi FROM company_assignment').fetchall())
    rash = []
    if E2:
        for inn in sorted(novye)[::9]:
            c = dict(k.execute('SELECT * FROM company WHERE inn=?', (inn,)).fetchone())
            d = E2.razbor_kompanii(c, cat.contacts(inn), cat, sales)
            if abs(float(score[inn]) - d['score']) > 0.05 or int(stup[inn]) != d['tier']:
                rash.append((inn, score[inn], d['score'], stup[inn], d['tier']))
    ok(E2 and not rash, 'балл очереди и ступень = формула fixF2_ball (каждая 9-я новая): расхождений %d %s' % (len(rash), rash[:3]))
    # рендер
    vnutr = next(z for z in vars(create_app()).values() if hasattr(z, 'routes') and hasattr(z, 'dependency_overrides'))
    USERS = {'meyer_admin': {'id': 0, 'username': 'meyer_admin', 'role': 'admin', 'is_active': 1}}
    for n_, p in enumerate(PRODAVCY, 1):
        USERS[p] = {'id': n_, 'username': p, 'role': 'sales', 'is_active': 1}
    kto = {'u': USERS['meyer_admin']}
    vnutr.dependency_overrides[rcs.current_user] = lambda: kto['u']

    def total(t):
        m = re.search(r'<b class="total-count">(\d+) компаний</b>', t)
        return int(m.group(1)) if m else -1
    with TestClient(vnutr) as kl:
        def get(u, kak='meyer_admin', **kw):
            kto['u'] = USERS[kak]
            return kl.get(PUT + u, follow_redirects=False, **kw)
        for nazv, u in (('главная', '/centro'), ('статистика', '/centro/stats')):
            o = get(u)
            ok(o.status_code == 200, 'админ, %s: %s' % (nazv, o.status_code))
        ok(total(get('/centro').text) == len(vse), 'админ, «Вся очередь»: %d' % total(get('/centro').text))
        for p in PRODAVCY:
            o = get('/centro', p)
            ok(o.status_code == 200 and total(o.text) == sch[p], '%s: главная %s, в очереди %d' % (p, o.status_code, total(o.text)))
        n_b = total(get('/centro', params={'baza': 'База 7'}).text)
        ok(n_b == len(novye), 'фильтр «Источник базы: База 7» (админ): %d' % n_b)
        primery = sorted(novye)[::90]
        for inn in primery:
            p = vlad[inn]
            for kak in ('meyer_admin', p):
                o = get('/centro', kak, params={'inn': inn})
                ok(o.status_code == 200 and 'contact-card' in o.text, 'карточка %s у %s: %s' % (inn, kak, o.status_code))
            drugoy = next(x for x in PRODAVCY if x != p)
            o = get('/centro', drugoy, params={'inn': inn})
            naim = k.execute('SELECT predpriyatie FROM company WHERE inn=?', (inn,)).fetchone()[0]
            ok(o.status_code != 200 or H.escape(naim) not in o.text, 'чужой %s не видит %s: %s' % (drugoy, inn, o.status_code))
    print('ПЛОХИХ ПРОВЕРОК: %d' % plohih[0])
    return plohih[0]


if '--proverka' in sys.argv:
    i = sys.argv.index('--proverka')
    raise SystemExit(1 if proverka(sys.argv[i + 1], sys.argv[i + 2]) else 0)


def zapustit_proverku(papka, sales_src=SALES, kat_src=KAT, metka=''):
    ts, tk = os.path.join(papka, 'test_sales.db'), os.path.join(papka, 'test_kat.db')
    kopiya(sales_src, ts)
    kopiya(kat_src, tk)
    r = subprocess.run([VENV, os.path.abspath(__file__), '--proverka', ts, tk], capture_output=True, timeout=1000, cwd=KOREN,
                       env=dict(os.environ, PYTHONIOENCODING='utf-8'))
    vyvod = r.stdout.decode('utf-8', 'replace') + r.stderr.decode('utf-8', 'replace')[-3000:]
    io.open(os.path.join(DROP, 'fixK-proverka%s-%s.txt' % (metka, time.strftime('%Y%m%d-%H%M%S'))), 'w', encoding='utf-8').write(vyvod)
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
    BEKAP = os.path.join(KOREN, '_bekap', 'fixK-' + VREMYA)
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
        print(zapustit_proverku(BEKAP, ts, tk, '-suhoy')[-4200:])
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
