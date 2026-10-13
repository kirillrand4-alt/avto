# -*- coding: utf-8 -*-
r"""fixQ: замена 330 «не покупателей Meyer» в панели Meyer (владелец 13.10: «не покупателей убрать и добрать», сохранить
270 у meyer1–4 и 120 у meyer5–9, равное качество, домашние регионы, холдинги; «неясно» – оставить с пометкой).

План (номера телефонов – только в нём) собирает локально fixQ_plan.py -> дроп fixQ-plan.json.
Шаги одной программы под замком C:\centro2\_zamok.txt (короткие транзакции, журнал «было/стало» – на дроп):
  1. сверка: новых нет ни в каталоге, ни в назначениях; сейчас 270/120; убираемые на месте и у тех же менеджеров;
     ПЕРЕПРОВЕРКА действий менеджеров (статус, комментарий, звонок, журнал, скрытие): если по убираемой они появились –
     её НЕ убираем (остаётся с пометкой в вердикте), а у этого менеджера не вставляем столько же новых (запас плана);
  2. каталог: убираемые – в arhiv_<таблица> с причиной (как fixH/fixK), удаление из рабочих таблиц;
     продажи: их назначения – в arhiv_company_assignment;
  3. продажи: назначения новых (ДО вставки в каталог – иначе панель раздала бы их сама); итог 270/120;
  4. каталог: колонки вердикта, новые компании («База 7 (замена 13.10)», все данные сборки, checko/DaData, Битрикс,
     паспорт), номера, люди, источники, строки холдингов; import_info;
  5. каталог: вердикт «покупатель Meyer» (meyer_verdikt, _napravlenie, _uverennost, _pochemu, _dokaz, _data) у ВСЕХ;
  6. флаги ЛПР и балл новых – по живым контактам, формула fixS_ball (метки Битрикса -> ступень не ниже 600);
  7. fixS_metki.py --primenit (метки Битрикса, идемпотентно), затем fixS_ball --tolko-ball (балл и ступень у всех);
  8. проверка – отдельным процессом на копиях баз (TestClient: админ и менеджеры).
Действия менеджеров (company_state, комментарии, звонки, activity_log) не трогаются. Код панели не меняется.

    python3 zapusk_na_servere.py fixQ_zamena.py --suhoy          # репетиция на копиях боевых баз (всё, кроме замка)
    python3 zapusk_na_servere.py fixQ_zamena.py --primenit       # запись под замком + метки + балл + проверка
    python3 zapusk_na_servere.py fixQ_zamena.py --tolko-proverka
Нужны рядом (C:\sender\_ops): 3s_fixS_metki.py и 3s_fixS_ball.py – текущие версии fixS (кладёт fixQ_polozhit).
"""
import collections
import contextlib
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
PLAN = os.path.join(DROP, 'fixQ-plan.json')
OPS = os.path.dirname(os.path.abspath(__file__))
METKI_PY = os.path.join(OPS, '3s_fixS_metki.py')
BITRIX_ZIP = os.path.join(DROP, 'fixS-bitrix-0910.zip')
ZAMOK = r'C:\centro2\_zamok.txt'
PUT = '/obzvon-meyer'
STARYE = ['meyer1', 'meyer2', 'meyer3', 'meyer4']
NOVYE_PR = ['meyer5', 'meyer6', 'meyer7', 'meyer8', 'meyer9']
PRODAVCY = STARYE + NOVYE_PR
ITOG = {p: (270 if p in STARYE else 120) for p in PRODAVCY}
SOURCE_VERSION = 'meyer-baza7-zamena-fixQ'
DEYSTVIYA = ('company_state', 'company_comment', 'zvonok_sobytie', 'activity_log', 'hidden_item')
VREMYA = time.strftime('%Y%m%d-%H%M%S')
METKA_ARHIVA = 'fixQ ' + time.strftime('%Y-%m-%d %H:%M:%S')
TABLICY = ('company', 'contact', 'person', 'company_source', 'holding_chlen', 'fact', 'signal')
VERDIKT = ('meyer_verdikt', 'meyer_verdikt_napravlenie', 'meyer_verdikt_uverennost', 'meyer_verdikt_pochemu',
           'meyer_verdikt_dokaz', 'meyer_verdikt_data')

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


def arhiv_tablica(k, t):
    kol = kolonki(k, t)
    k.execute('CREATE TABLE IF NOT EXISTS arhiv_%s AS SELECT * FROM %s WHERE 0' % (t, t))
    est = set(kolonki(k, 'arhiv_' + t))
    for c in kol + ['arhiv_prichina', 'arhiv_data']:
        if c not in est:
            k.execute('ALTER TABLE arhiv_%s ADD COLUMN "%s" TEXT' % (t, c))
    return kol


def zamok_vzyat(kto):
    if os.path.exists(ZAMOK) and time.time() - os.path.getmtime(ZAMOK) > 1500:
        os.remove(ZAMOK)
    try:
        fd = os.open(ZAMOK, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        print('ЗАМОК ЗАНЯТ: ' + io.open(ZAMOK, encoding='utf-8').read())
        raise SystemExit(3)
    os.write(fd, ('%s %s' % (kto, time.strftime('%H:%M:%S'))).encode('utf-8'))
    os.close(fd)


def zamok_obnovit():
    try:
        os.utime(ZAMOK, None)
    except OSError:
        pass


def zamok_otdat():
    try:
        os.remove(ZAMOK)
    except OSError:
        pass


def E2_modul():
    sys.path.insert(0, OPS)
    return __import__('3s_fixS_ball')


def kesh_obshchih(cat):
    """Общий номер панели считается один раз на прогон (каталог в цикле не меняется)."""
    orig = cat._shared_phone_keys
    kesh = {}

    def _sh(conn):
        if 'k' not in kesh:
            kesh['k'] = orig(conn)
        return kesh['k']
    cat._shared_phone_keys = _sh
    return orig


def flagi(cat, items):        # = fixK_m7.flagi = fixK_zalivka.flagi
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
    zh = {'vremya': VREMYA, 'suhoy': bool(suhoy_metka), 'metka_arhiva': METKA_ARHIVA, 'ubrano': {}, 'naznacheniya_ubrany': [],
          'ostavleny_s_deystviyami': {}, 'ne_vstavleny': [], 'naznacheniya': [], 'kolonki_dobavleny': [], 'vstavleno': {},
          'verdikt': [], 'flagi': [], 'ball': [], 'oshibki': []}
    prodavec = dict(plan['prodavcy'])
    ubrat = dict(plan['ubrat'])
    k = podkl(KAT)
    s = podkl(SALES)
    # ---------- 1. сверка и перепроверка действий менеджеров
    vlad = dict(s.execute('SELECT inn, username FROM company_assignment').fetchall())
    v_kat = {r[0] for r in k.execute('SELECT inn FROM company')}
    users = {r['username']: dict(r) for r in s.execute('SELECT username, role, is_active FROM users')}
    osh = []
    novye_vse = {c['inn'] for c in plan['kompanii']}
    if novye_vse & v_kat:
        osh.append('новые уже в каталоге: %s' % sorted(novye_vse & v_kat)[:10])
    if novye_vse & set(vlad):
        osh.append('у новых уже есть назначения: %s' % sorted(novye_vse & set(vlad))[:10])
    sch = collections.Counter(vlad.values())
    if any(sch[p] != ITOG[p] for p in PRODAVCY):
        osh.append('распределение сейчас не 270×4 и 120×5: %s' % dict(sch))
    for p in PRODAVCY:
        if p not in users or users[p]['role'] != 'sales' or not users[p]['is_active']:
            osh.append('менеджера %s нет или не активен' % p)
    for u, e in plan['edinicy'].items():
        p_u = prodavec[e['novye'][0]]
        for j in e['panel']:
            if vlad.get(j) != p_u:
                osh.append('компания панели %s (группа новых %s) сейчас у %s, а группа идёт к %s' % (j, e['novye'], vlad.get(j), p_u))
    for inn, u in ubrat.items():
        if vlad.get(inn) != u['prodavec'] or inn not in v_kat:
            osh.append('убираемая %s: сейчас у %s, в каталоге %s (план: у %s)' % (inn, vlad.get(inn), inn in v_kat, u['prodavec']))
    dz = zakrep(s, list(ubrat))
    if dz:
        # владелец/задание 13.10: появились действия менеджера – не убирать, оставить с пометкой; у менеджера на одну новую меньше
        zapas = {p: list(v) for p, v in plan['zapas'].items()}
        for inn in sorted(dz):
            p = ubrat[inn]['prodavec']
            if not zapas.get(p):
                osh.append('по убираемой %s есть действия (%s), а запаса новых у %s нет' % (inn, dz[inn], p))
                continue
            ne_vst = zapas[p].pop(0)
            zh['ostavleny_s_deystviyami'][inn] = {'prodavec': p, 'deystviya': dz[inn], 'vmesto_novoy_ne_vstavlena': ne_vst}
            zh['ne_vstavleny'].append(ne_vst)
            del ubrat[inn]
            del prodavec[ne_vst]
    if osh:
        print('ОСТАНОВКА, ничего не изменено:\n  ' + '\n  '.join(osh))
        raise SystemExit(4)
    novye = {c['inn']: c for c in plan['kompanii'] if c['inn'] in prodavec}
    print('сверка: новых %d, в каталоге сейчас %d, назначения %s; убрать в архив %d; оставлены (есть действия) %d %s' % (
        len(novye), len(v_kat), dict(sch), len(ubrat), len(zh['ostavleny_s_deystviyami']), sorted(zh['ostavleny_s_deystviyami'])))

    # ---------- 2. убрать в архив (как fixH/fixK: arhiv_* с причиной)
    if ubrat:
        ph = ','.join('?' * len(ubrat))
        nachat(k)
        try:
            for t_ in TABLICY:
                kol = arhiv_tablica(k, t_)
                sk = ','.join('"%s"' % c for c in kol)
                n_do = k.execute('SELECT COUNT(*) FROM %s WHERE inn IN (%s)' % (t_, ph), list(ubrat)).fetchone()[0]
                n_a = 0
                for inn, u in ubrat.items():
                    cur = k.execute('INSERT INTO arhiv_%s (%s, arhiv_prichina, arhiv_data) SELECT %s, ?, ? FROM %s WHERE inn=?'
                                    % (t_, sk, sk, t_), ((u['prichina'] + '; была у ' + u['prodavec'])[:900], METKA_ARHIVA, inn))
                    n_a += cur.rowcount
                zh['ubrano'][t_] = [dict(r) for r in k.execute('SELECT * FROM %s WHERE inn IN (%s)' % (t_, ph), list(ubrat))]
                cur = k.execute('DELETE FROM %s WHERE inn IN (%s)' % (t_, ph), list(ubrat))
                if not (n_do == n_a == cur.rowcount):
                    raise RuntimeError('%s: было %d, в архив %d, удалено %d' % (t_, n_do, n_a, cur.rowcount))
            k.commit()
        except BaseException:
            k.rollback()
            raise
        nachat(s)
        try:
            kol_a = arhiv_tablica(s, 'company_assignment')
            sk = ','.join('"%s"' % c for c in kol_a)
            for inn, u in ubrat.items():
                s.execute('INSERT INTO arhiv_company_assignment (%s, arhiv_prichina, arhiv_data) SELECT %s, ?, ? FROM company_assignment '
                          'WHERE inn=?' % (sk, sk), ((u['prichina'] + '; была у ' + u['prodavec'])[:900], METKA_ARHIVA, inn))
            zh['naznacheniya_ubrany'] = [dict(r) for r in s.execute('SELECT * FROM company_assignment WHERE inn IN (%s)' % ph, list(ubrat))]
            if zakrep(s, list(ubrat)):
                raise RuntimeError('по убираемым появились действия менеджеров во время записи')
            if s.execute('DELETE FROM company_assignment WHERE inn IN (%s)' % ph, list(ubrat)).rowcount != len(ubrat):
                raise RuntimeError('назначения убираемых удалены не все')
            s.commit()
        except BaseException:
            s.rollback()
            raise
        print('в архив (arhiv_*, метка «%s»): %d компаний; строк: %s' % (
            METKA_ARHIVA, len(ubrat), {t_: len(v) for t_, v in zh['ubrano'].items()}))

    # ---------- 3. продажи: назначения новых ДО каталога
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
                 'assigned_by': 'База 7 (замена 13.10, fixQ): вместо не покупателей Meyer – столько же, холдинги и домашние регионы',
                 'stupen_ocheredi': st['tier']}
            a = {kk: v for kk, v in a.items() if kk in kol_a}
            s.execute('INSERT INTO company_assignment (%s) VALUES (%s)' % (','.join(a), ','.join('?' * len(a))), list(a.values()))
            zh['naznacheniya'].append(a)
        sch2 = collections.Counter(r[0] for r in s.execute('SELECT username FROM company_assignment'))
        if any(sch2[p] != ITOG[p] for p in PRODAVCY):
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
        print('АВАРИЯ: назначения замены удалены (%d); убранные остаются в архиве (журнал на дропе)' % n)

    # ---------- 4. каталог: колонки, компании, номера, люди, источники, холдинги
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
            if x['inn'] not in novye:
                continue
            r = {kk: v for kk, v in x.items() if kk in kk_}
            cur = k.execute('INSERT INTO contact (%s) VALUES (%s)' % (','.join(r), ','.join('?' * len(r))), list(r.values()))
            zh['vstavleno']['contact'].append(cur.lastrowid)
        for x in plan['lyudi']:
            if x['inn'] not in novye:
                continue
            r = {kk: v for kk, v in x.items() if kk in kp}
            cur = k.execute('INSERT INTO person (%s) VALUES (%s)' % (','.join(r), ','.join('?' * len(r))), list(r.values()))
            zh['vstavleno']['person'].append(cur.lastrowid)
        for x in plan['istochniki']:
            if x['inn'] not in novye:
                continue
            cur = k.execute('INSERT INTO company_source (inn, field_name, source, source_url) VALUES (?,?,?,?)',
                            (x['inn'], x['field_name'], x['source'], x['source_url']))
            zh['vstavleno']['company_source'].append(cur.lastrowid)
        kh = set(kolonki(k, 'holding_chlen'))
        for x in plan['holding_chlen']:
            if x['inn'] not in novye and x['inn'] not in v_kat:
                continue
            r = {kk: v for kk, v in x.items() if kk in kh}
            k.execute('INSERT INTO holding_chlen (%s) VALUES (%s)' % (','.join(r), ','.join('?' * len(r))), list(r.values()))
            zh['vstavleno']['holding_chlen'].append([x['gruppa'], x['inn']])
        for kk, v in {'fixQ_zamena': VREMYA, 'fixQ_dobavleno': ','.join(sorted(novye)), 'fixQ_ubrano': ','.join(sorted(ubrat)),
                      'fixQ_baza': plan['baza'], 'fixQ_kompaniy_novyh': str(len(novye))}.items():
            k.execute('INSERT OR REPLACE INTO import_info (key, value) VALUES (?,?)', (kk, v))
        n = k.execute('SELECT COUNT(*) FROM company').fetchone()[0]
        if n != len(v_kat) - len(ubrat) + len(novye):
            raise RuntimeError('в каталоге %d компаний (ждали %d)' % (n, len(v_kat) - len(ubrat) + len(novye)))
        k.commit()
    except BaseException:
        k.rollback()
        ubrat_naznacheniya()
        raise
    print('каталог: колонки добавлены %s; новых – компаний %d, номеров %d, людей %d, источников %d, строк холдингов %d' % (
        zh['kolonki_dobavleny'], len(zh['vstavleno']['company']), len(zh['vstavleno']['contact']),
        len(zh['vstavleno']['person']), len(zh['vstavleno']['company_source']), len(zh['vstavleno']['holding_chlen'])))

    # ---------- 5. вердикт «покупатель Meyer» у всех компаний панели
    nachat(k)
    try:
        for inn in sorted({r[0] for r in k.execute('SELECT inn FROM company')}):
            v = plan['verdikty'].get(inn)
            if not v:
                zh['oshibki'].append('%s: вердикта в плане нет' % inn)
                continue
            v = dict(v)
            if inn in zh['ostavleny_s_deystviyami']:
                v['meyer_verdikt_pochemu'] = ('оставлена: по компании уже есть действия менеджера, поэтому не убрана; '
                                              + (v.get('meyer_verdikt_pochemu') or ''))[:1500]
            tek = dict(k.execute('SELECT %s FROM company WHERE inn=?' % ', '.join(VERDIKT), (inn,)).fetchone())
            izm = {p: v[p] for p in VERDIKT if tek.get(p) != v[p]}
            if izm:
                k.execute('UPDATE company SET %s WHERE inn=?' % ', '.join('"%s"=?' % p for p in izm), list(izm.values()) + [inn])
                zh['verdikt'].append({'inn': inn, 'bylo': {p: tek.get(p) for p in izm}, 'stalo': izm})
        k.commit()
    except BaseException:
        k.rollback()
        raise
    print('вердикт записан/обновлён у %d компаний; без вердикта в плане %d' % (len(zh['verdikt']), len(zh['oshibki'])))

    # ---------- 6. флаги ЛПР, search_blob – по живым контактам карточки; балл и ступень новых – формула fixS_ball
    E2 = E2_modul()
    orig = kesh_obshchih(cat)
    obnov = {}
    try:
        for inn in novye:
            c = dict(k.execute('SELECT * FROM company WHERE inn=?', (inn,)).fetchone())
            items = cat.contacts(inn)
            nov = flagi(cat, items)
            c2 = dict(c, **nov)
            d = E2.razbor_kompanii(c2, items, cat, sales)
            nov['moy_prioritet'], nov['prioritet_pochemu'], nov['stupen_prichina'] = d['ball'], d['pochemu'], d['stupen_prichina']
            if d['tier'] != plan['stupeni'][inn]['tier'] or abs(d['score'] - plan['stupeni'][inn]['score']) > 0.05:
                zh['oshibki'].append('%s: на сервере ступень %d балл %.1f, в плане %d %.1f' % (
                    inn, d['tier'], d['score'], plan['stupeni'][inn]['tier'], plan['stupeni'][inn]['score']))
            obnov[inn] = (c, nov, {'score': d['score'], 'tier': d['tier']})
    finally:
        cat._shared_phone_keys = orig
    nachat(k)
    try:
        for inn, (c, nov, st) in obnov.items():
            izm = {p: v for p, v in nov.items() if c.get(p) != v}
            if izm:
                k.execute('UPDATE company SET %s WHERE inn=?' % ', '.join('"%s"=?' % p for p in izm), list(izm.values()) + [inn])
                zh['flagi'].append({'inn': inn, 'bylo': {p: c.get(p) for p in izm}, 'stalo': izm})
        k.commit()
    except BaseException:
        k.rollback()
        raise
    nachat(s)
    try:
        for inn, (c, nov, st) in obnov.items():
            s.execute('UPDATE company_assignment SET has_phone=?, has_purchaser=?, has_tech=?, assignment_score=?, stupen_ocheredi=? '
                      'WHERE inn=? AND source_version=?', (nov['has_phone'], nov['has_purchaser'], nov['has_tech'], st['score'],
                                                           st['tier'], inn, SOURCE_VERSION))
            zh['ball'].append({'inn': inn, 'score': st['score'], 'tier': st['tier']})
        s.commit()
    except BaseException:
        s.rollback()
        raise
    print('флаги: изменились у %d (план считал на копии); балл/ступень новых по fixS_ball: %d; расхождений с планом: %d %s' % (
        len(zh['flagi']), len(zh['ball']), sum(1 for x in zh['oshibki'] if 'в плане' in x), [x for x in zh['oshibki'] if 'в плане' in x][:4]))
    k.close()
    s.close()
    put = os.path.join(DROP, 'fixQ-zhurnal-%s%s.json' % (VREMYA, suhoy_metka))
    io.open(put, 'w', encoding='utf-8').write(json.dumps(zh, ensure_ascii=False, indent=0, default=str))
    print('журнал «было/стало»: %s' % put)
    return zh


def metki_i_ball(KAT_, SALES_, papka, suhoy_metka):
    """fixS_metki --primenit, затем fixS_ball.primenit(tolko_ball) – на тех же базах (живых или копиях)."""
    env = dict(os.environ, PYTHONIOENCODING='utf-8')
    if suhoy_metka:
        env.update(FIXS_KOREN=papka, FIXS_KAT=KAT_, FIXS_SALES=SALES_, FIXS_DROP=papka)
    r = subprocess.run([sys.executable, METKI_PY, '--primenit', '--zip', BITRIX_ZIP], capture_output=True, timeout=900,
                       cwd=OPS, env=env)
    v = r.stdout.decode('utf-8', 'replace')
    io.open(os.path.join(DROP, 'fixQ-metki-%s%s.txt' % (VREMYA, suhoy_metka)), 'w', encoding='utf-8').write(
        v + '\n' + r.stderr.decode('utf-8', 'replace')[-3000:])
    if r.returncode:
        raise RuntimeError('fixS_metki: rc=%s %s' % (r.returncode, r.stderr.decode('utf-8', 'replace')[-800:]))
    print('fixS_metki: %s' % ' | '.join(x for x in v.splitlines() if x.startswith(('ВСЕГО', 'активных', 'компаний с изменениями',
                                                                                     'записано', 'пробел')))[:900])
    zamok_obnovit()
    from app.services import centro_catalog as cat
    E2 = E2_modul()
    orig = kesh_obshchih(cat)
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            E2.primenit(False, True, KAT=KAT_, SALES=SALES_, metka=('-fixQ' + suhoy_metka) if suhoy_metka else '')
    finally:
        cat._shared_phone_keys = orig
    t = buf.getvalue()
    io.open(os.path.join(DROP, 'fixQ-ball-%s%s.txt' % (VREMYA, suhoy_metka)), 'w', encoding='utf-8').write(t)
    print('fixS_ball --tolko-ball: %s' % ' | '.join(x for x in t.splitlines() if x.startswith(('база продаж', 'журнал', 'ступени было')) or
                                                    x.strip().startswith('ВСЕГО'))[:900])
    zamok_obnovit()


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
    novye = {i for i in plan['prodavcy'] if i in vse}
    ne_vst = set(plan['prodavcy']) - novye
    sch = collections.Counter(vlad[i] for i in vse if i in vlad)
    ok(set(vlad) == vse and all(sch[p] == ITOG[p] for p in PRODAVCY),
       'назначения = каталог (%d); у менеджеров %s' % (len(vse), dict(sorted(sch.items()))))
    sch_n = collections.Counter(vlad[i] for i in novye)
    ok(all(sch_n[p] + sum(1 for i in ne_vst if plan['prodavcy'][i] == p) == plan['cel'][p] for p in PRODAVCY),
       'новых по квотам %s: %s (не вставлено из-за действий: %d)' % (plan['cel'], dict(sorted(sch_n.items())), len(ne_vst)))
    ub = list(plan['ubrat'])
    ost = [i for i in ub if i in vse]
    n_a = k.execute('SELECT COUNT(DISTINCT inn) FROM arhiv_company WHERE inn IN (%s)' % ','.join('?' * len(ub)), ub).fetchone()[0]
    n_aa = s.execute('SELECT COUNT(DISTINCT inn) FROM arhiv_company_assignment WHERE inn IN (%s)' % ','.join('?' * len(ub)), ub).fetchone()[0]
    ok(len(ost) == len(ne_vst) and n_a >= len(ub) - len(ost) and n_aa >= len(ub) - len(ost),
       'из %d убираемых в рабочем каталоге %d (оставлены с действиями); в arhiv_company %d, в arhiv_company_assignment %d' % (
           len(ub), len(ost), n_a, n_aa))
    ok(all(vlad.get(i) == plan['prodavcy'][i] for i in novye), 'новые – у менеджеров по плану')
    for reg, kto in plan['dom'].items():
        c = collections.Counter(vlad.get(i) for i in vse if region[i] == reg)
        ok(set(c) <= set(kto), 'домашний регион %s (%d): %s – только %s' % (reg, sum(c.values()), dict(sorted(c.items())), kto))
    akt = set(plan.get('aktivnye_meyer_inn') or [])
    ok(not (vse & akt), 'компаний с активной сделкой Meyer в каталоге: %d %s' % (len(vse & akt), sorted(vse & akt)[:5]))
    razorv = []
    for g in {r[0] for r in k.execute("SELECT DISTINCT gruppa FROM holding_chlen WHERE gruppa NOT LIKE 'snyato%'")}:
        chl = [r[0] for r in k.execute('SELECT inn FROM holding_chlen WHERE gruppa=?', (g,)) if r[0] in vse]
        if len({vlad.get(i) for i in chl}) > 1:
            razorv.append((g, chl))
    for u, e in plan['edinicy'].items():
        chl = [i for i in e['novye'] + e['panel'] if i in vse]
        if len({vlad.get(i) for i in chl}) > 1:
            razorv.append((u, chl, [vlad.get(i) for i in chl]))
    ok(not razorv, 'холдинги (каталог) и группы новых с общими номерами/сайтом – у одного менеджера%s' % (
        (': разорваны %s' % razorv[:4]) if razorv else ''))
    n_b = k.execute('SELECT COUNT(*) FROM company WHERE bazy=?', (plan['baza'],)).fetchone()[0]
    ok(n_b == len(novye), 'метка «%s»: %d' % (plan['baza'], n_b))
    n_k = k.execute('SELECT COUNT(*) FROM contact WHERE inn IN (%s)' % ','.join('?' * len(novye)), list(novye)).fetchone()[0]
    n_kp = sum(1 for x in plan['kontakty'] if x['inn'] in novye)
    ok(n_k == n_kp, 'номеров новых в каталоге %d = план %d' % (n_k, n_kp))
    nv = collections.Counter(r[0] for r in k.execute('SELECT meyer_verdikt FROM company'))
    ok(sum(nv.values()) == len(vse) and not nv.get(None) and not nv.get(''), 'вердикт у всех %d: %s' % (len(vse), dict(nv)))
    nd = k.execute("SELECT COUNT(*) FROM company WHERE meyer_verdikt_data='13.10.2026'").fetchone()[0]
    ok(nd == len(vse), 'дата вердикта 13.10.2026 у %d' % nd)
    E2 = E2_modul()
    score = dict(s.execute('SELECT inn, assignment_score FROM company_assignment').fetchall())
    stup = dict(s.execute('SELECT inn, stupen_ocheredi FROM company_assignment').fetchall())
    orig = kesh_obshchih(cat)
    rash = []
    proba = sorted(novye)[::7] + sorted(vse - novye)[::40]
    for inn in proba:
        c = dict(k.execute('SELECT * FROM company WHERE inn=?', (inn,)).fetchone())
        d = E2.razbor_kompanii(c, cat.contacts(inn), cat, sales)
        if abs(float(score[inn]) - d['score']) > 0.05 or int(stup[inn]) != d['tier']:
            rash.append((inn, score[inn], d['score'], stup[inn], d['tier']))
    cat._shared_phone_keys = orig
    ok(not rash, 'балл очереди и ступень = формула fixS_ball (%d проб: каждая 7-я новая, каждая 40-я прочая): расхождений %d %s' % (
        len(proba), len(rash), rash[:3]))
    st_n = collections.Counter(stup[i] for i in novye)
    ok(True, 'ступени новых: %s' % {800: st_n[4], 600: st_n[3], 400: st_n[2], 200: st_n[1], 0: st_n[0]})
    vnutr = next(z for z in vars(create_app()).values() if hasattr(z, 'routes') and hasattr(z, 'dependency_overrides'))
    USERS = {'meyer_admin': {'id': 0, 'username': 'meyer_admin', 'role': 'admin', 'is_active': 1}}
    for n_, p in enumerate(PRODAVCY, 1):
        USERS[p] = {'id': n_, 'username': p, 'role': 'sales', 'is_active': 1}
    kto = {'u': USERS['meyer_admin']}
    vnutr.dependency_overrides[rcs.current_user] = lambda: kto['u']
    skr = {str(r[0]) for r in s.execute("SELECT inn FROM hidden_item WHERE kind='company'")}

    def total(t):
        m = re.search(r'<b class="total-count">(\d+) компаний</b>', t)
        return int(m.group(1)) if m else -1

    def opciya(t, imya, znach):
        m = re.search(r'<select name="%s">.*?</select>' % imya, t, re.S)
        if not m:
            return -1
        m2 = re.search(r'<option value="%s"[^>]*>[^<]*· (\d+)</option>' % re.escape(H.escape(znach)), m.group(0))
        return int(m2.group(1)) if m2 else -1
    with TestClient(vnutr) as kl:
        def get(u, kak='meyer_admin', **kw):
            kto['u'] = USERS[kak]
            return kl.get(PUT + u, follow_redirects=False, **kw)
        for nazv, u in (('главная', '/centro'), ('статистика', '/centro/stats'), ('CSV', '/centro/vygruzka.csv')):
            o = get(u)
            ok(o.status_code == 200, 'админ, %s: %s' % (nazv, o.status_code))
        glav = get('/centro').text
        ok(total(glav) == len(vse - skr), 'админ, «Вся очередь»: %d (ждали %d)' % (total(glav), len(vse - skr)))
        n_opc = opciya(glav, 'baza', plan['baza'])
        n_f = total(get('/centro', params={'baza': plan['baza']}).text)
        ok(n_f == len(novye - skr) and n_opc == n_f, 'фильтр «Источник базы: %s» (админ): число в списке %d = строк %d = новых %d' % (
            plan['baza'], n_opc, n_f, len(novye - skr)))
        for p in PRODAVCY:
            o = get('/centro', p)
            n_p = total(o.text)
            moi_n = {i for i in novye if vlad[i] == p} - skr
            n_opc = opciya(o.text, 'baza', plan['baza'])
            n_f = total(get('/centro', p, params={'baza': plan['baza']}).text)
            ok(o.status_code == 200 and n_p == sch[p] - len({i for i in skr if vlad.get(i) == p}) and n_opc == n_f == len(moi_n),
               '%s: главная %s, в очереди %d; «%s» число %d = строк %d = новых %d' % (p, o.status_code, n_p, plan['baza'], n_opc, n_f, len(moi_n)))
        for inn in ub[::33]:
            if inn in vse:
                continue
            o = get('/centro', params={'inn': inn})
            naim = plan['ubrat'][inn]['nazvanie']
            ok(o.status_code != 200 or ('contact-card' not in o.text or H.escape(naim) not in o.text.split('<h1>', 1)[-1][:400]),
               'убранная %s не открывается в рабочей панели: %s' % (inn, o.status_code))
        primery = sorted(novye)[::40]
        for inn in primery:
            p = vlad[inn]
            for kak in ('meyer_admin', p):
                o = get('/centro', kak, params={'inn': inn})
                ok(o.status_code == 200 and 'contact-card' in o.text, 'карточка новой %s у %s: %s' % (inn, kak, o.status_code))
            drugoy = next(x for x in PRODAVCY if x != p)
            o = get('/centro', drugoy, params={'inn': inn})
            naim = k.execute('SELECT predpriyatie FROM company WHERE inn=?', (inn,)).fetchone()[0]
            ok(o.status_code != 200 or H.escape(naim) not in o.text, 'чужой %s не видит %s: %s' % (drugoy, inn, o.status_code))
        o = get('/centro/stats')
        ok(o.status_code == 200, 'админ, статистика после всего: %s' % o.status_code)
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
    io.open(os.path.join(DROP, 'fixQ-proverka%s-%s.txt' % (metka, time.strftime('%Y%m%d-%H%M%S'))), 'w', encoding='utf-8').write(vyvod)
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
    BEKAP = os.path.join(KOREN, '_bekap', 'fixQ-' + VREMYA)
    os.makedirs(BEKAP, exist_ok=True)
    if '--tolko-proverka' in sys.argv:
        print(zapustit_proverku(BEKAP)[-5500:])
        raise SystemExit(0)
    for f in (METKI_PY, os.path.join(OPS, '3s_fixS_ball.py'), BITRIX_ZIP, PLAN):
        if not os.path.exists(f):
            raise SystemExit('нет файла %s' % f)
    plan = json.load(io.open(PLAN, encoding='utf-8'))
    if '--suhoy' in sys.argv:
        tk, ts = os.path.join(BEKAP, 'suhoy_kat.db'), os.path.join(BEKAP, 'suhoy_sales.db')
        kopiya(KAT, tk)
        kopiya(SALES, ts)
        for kk in ('CENTRIFUGAL_DB', 'CENTRO_DB', 'PARK_OCHERED_DB'):
            os.environ[kk] = tk
        for kk in ('CENTRO_SALES_DB', 'PARK_OCHERED_SALES_DB'):
            os.environ[kk] = ts
        t0 = time.time()
        rabota(tk, ts, plan, '-suhoy')
        metki_i_ball(tk, ts, BEKAP, '-suhoy')
        print('===== ПРОВЕРКА РЕПЕТИЦИИ (на копиях; %.0f с) =====' % (time.time() - t0))
        print(zapustit_proverku(BEKAP, ts, tk, '-suhoy')[-3800:])
        for f in (tk, ts):
            try:
                os.remove(f)
            except OSError:
                pass
        raise SystemExit(0)
    if '--primenit' not in sys.argv:
        raise SystemExit('нужен --suhoy, --primenit или --tolko-proverka')
    assert os.path.normcase(os.environ.get('CENTRIFUGAL_DB', '')) == os.path.normcase(KAT)
    assert os.path.normcase(os.environ.get('CENTRO_SALES_DB', '')) == os.path.normcase(SALES)
    zamok_vzyat('fixQ (замена 330 не покупателей Meyer: архив, заливка, вердикты, метки, балл)')
    try:
        kopiya(KAT, os.path.join(BEKAP, 'meyer_baza1.db'))
        kopiya(SALES, os.path.join(BEKAP, 'centro_sales_meyer1.db'))
        print('копии баз (НЕ для отката целиком): %s' % BEKAP)
        t0 = time.time()
        rabota(KAT, SALES, plan)
        zamok_obnovit()
        metki_i_ball(KAT, SALES, BEKAP, '')
        print('запись, метки и балл: %.0f с' % (time.time() - t0))
    finally:
        zamok_otdat()
    print('===== ПРОВЕРКА (на копиях баз после записи) =====')
    print(zapustit_proverku(BEKAP)[-3500:])
