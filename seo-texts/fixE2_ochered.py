# -*- coding: utf-8 -*-
"""fixE2: балл и ступень очереди Meyer заново + раздача (холдинг одному продавцу, равенство
очередей по качеству). Один файл на оба места: локально считает план (MILP через scipy),
на сервере применяет его к боевой базе продаж.

БАЛЛ («Важность», company.moy_prioritet) – та же шкала, что при заливке Баз 1–6
(panel_meyer_v_json.py, meyer_baza{2,3,4,6}_v_json.py), но на НОВЫХ данных:
  выручка          0..40  – 10 x lg(выручка / 10 млн); выручка – после checko (vyruchka_rub)
  попадание        20     – сегмент по основному ОКВЭД (popadanie после E1), иначе 0
  лучший контакт   ЛПР (роль по смыслу должности – centro_catalog.rol_kontakta агента C):
                     первое лицо, техдиректор/гл. инженер, гл. механик/энергетик,
                     производство, гл. технолог 20; снабжение 15; коммерческий директор и
                     «ЛПР со слов продавца» 10; +10 ФИО; +5 личный мобильный / +3 с добавочным;
                   без ЛПР: приёмная / общий номер 5, иначе 0;
                   +5 сайт свой (проверка «чей сайт» агента D: свой / группа) или номер
                   сверен со страницей («верно» / «исправлено»); −10 «проверить».
                   Не ЛПР: номер с чужой страницы (chuzhoy_istochnik), битый, «не номер
                   компании», закупки сырья, продажи, кадры, бухгалтерия, факс и т. п.
  ещё ЛПР          5 за каждого ЛПР с телефоном сверх первого (по людям), не больше 10
  сегменты         5 за каждый сегмент сверх первого, не больше 15
БАЛЛ ОЧЕРЕДИ (company_assignment.assignment_score – по нему сортирует _queue_rank, его
показывают список, карточка, статистика и CSV) = ступень + company_score() панели
(Важность + её надбавки: телефон, закупщик, техник +2, раздел ОКВЭД производства +25,
ликвидация −1000). Ступень – сотни, чтобы порядок не зависел от выручки:
  800 ЛПР с ФИО и личным мобильным · 600 ЛПР с личным мобильным · 400 ЛПР с рабочим /
  добавочным (или 8-800, общим номером) · 200 ЛПР не найден · 0 пометка очереди
  («нецелевая» / «недействующая» – в самом конце).
Показанное число и порядок совпадают: в пределах вкладки и одинакового «следующего
контакта» больше – выше (та же функция _queue_rank у списка, статистики и CSV).

    локально:  python3 fixE2_ochered.py --plan <каталог.db> <продажи.db> <корень с app> \
                   <fixD-holdingi.json> <выход-план.json>
    сервер:    python3 zapusk_na_servere.py fixE2_ochered.py --primenit [--suhoy]
               (план – C:\\seostat\\drop\\drop-storage\\fixE2-plan.json)
"""
import collections
import io
import json
import math
import os
import re
import sqlite3
import subprocess
import sys
import time

PRODAVCY = ['meyer1', 'meyer2', 'meyer3', 'meyer4']
STUPEN = {4: 800, 3: 600, 2: 400, 1: 200, 0: 0}
STUPEN_NAZV = {4: 'ЛПР с ФИО и личным мобильным', 3: 'ЛПР с личным мобильным',
               2: 'ЛПР с рабочим / добавочным', 1: 'ЛПР не найден', 0: 'пометка очереди – в конце'}
BAZY = ['База 1', 'База 2', 'База 3', 'База 4', 'База 6']
SILNYE_UROVNI = {1, 2, 3, 4, 5}      # первое лицо … главный технолог


# ====================================================================== балл компании
def razbor_kompanii(c, items, cat, sales):
    """c – строка company (dict), items – cat.contacts(inn). -> словарь балла и метрик."""
    tel = [x for x in items if x['kind'] == 'phone']
    lpr = [x for x in tel if x['lpr']]
    mob = [x for x in lpr if x['vid_nomera'] == 'мобильный']
    fio_mob = [x for x in mob if x['person']]
    pometka = str(c.get('pometka_ocheredi') or '').strip()
    if pometka:
        tier = 0
    elif fio_mob:
        tier = 4
    elif mob:
        tier = 3
    elif lpr:
        tier = 2
    else:
        tier = 1
    if lpr:
        t_lpr = 4 if fio_mob else 3 if mob else 2
    else:
        t_lpr = 1

    vyr = c.get('vyruchka_rub')
    try:
        vyr = float(vyr) if vyr not in (None, '') else None
    except (TypeError, ValueError):
        vyr = None
    b_vyr = max(0.0, min(40.0, 10 * math.log10(vyr / 1e7))) if vyr and vyr > 0 else 0.0
    b_pop = 20 if str(c.get('popadanie') or '').strip() == 'основной ОКВЭД' else 0
    sayt_ok = str(c.get('proverka_sayta') or '').strip() in ('свой', 'группа')

    def ball_kontakta(x):
        if x['lpr']:
            u = x['uroven']
            b = 20 if u in SILNYE_UROVNI else 15 if u == 6 else 10
            if x['person']:
                b += 10
            b += 5 if x['vid_nomera'] == 'мобильный' else 3 if x['vid_nomera'] == 'рабочий с добавочным' else 0
        else:
            b = 5 if (not lpr and x['rol_vid'] in ('приёмная', 'общий номер')) else 0
        src = str(x.get('source') or '')
        if sayt_ok or re.search(r'верно|исправлено', src):
            b += 5
        if 'проверить' in src:
            b -= 10
        return b
    kandidaty = lpr or [x for x in tel if x['vid_nomera'] not in ('битый номер', 'не номер компании')
                        and x['rol_vid'] not in ('с сайта другого юрлица', 'битый номер', 'не номер компании')]
    luchshiy = max(kandidaty, key=ball_kontakta) if kandidaty else None
    b_kont = ball_kontakta(luchshiy) if luchshiy else 0
    lyudi = {cat._kl_fio(x['person']) if x['person'] else 'n' + cat._phone_key(x['value']) for x in lpr}
    b_esche = min(10, 5 * max(0, len(lyudi) - 1))
    segm = [v.strip() for v in str(c.get('segment') or '').split('|') if v.strip()]
    b_segm = min(15, 5 * max(0, len(segm) - 1))
    ball = round(b_vyr + b_pop + b_kont + b_esche + b_segm, 1)

    z = dict(c)
    z['moy_prioritet'] = ball
    nadb_c = sales.company_score(z)
    score = round(STUPEN[tier] + nadb_c, 1)
    nadb = round(nadb_c - ball, 1)
    pochemu = ('ступень %d (%s) · выручка %+.0f · попадание %+d · лучший контакт %+d · ещё ЛПР %+d · '
               'сегменты %+d = важность %.1f · надбавки панели %+.1f → балл очереди %.1f'
               % (STUPEN[tier], STUPEN_NAZV[tier], b_vyr, b_pop, b_kont, b_esche, b_segm, ball, nadb, score))
    if tier == 0:
        pochemu += ' · %s' % pometka
    bz = [b.strip() for b in str(c.get('bazy') or '').split('|') if b.strip()]
    return {
        'inn': c['inn'], 'tier': tier, 't_lpr': t_lpr, 'ball': ball, 'score': score, 'pochemu': pochemu,
        'vyr': vyr, 'tech': int(any(x['is_tech'] for x in lpr)), 'lpr_fio': int(any(x['person'] for x in lpr)),
        'klient_sc': int(str(c.get('bitrix_klient_sc') or '').strip() not in ('', '0', '0.0', 'None')),
        'bitrix': int(bool(c.get('bitrix_kc')) or float(c.get('bitrix_sdelok') or 0) > 0),
        'pometka': int(bool(pometka)), 'bazy': bz, 'region': c.get('region') or '',
        'has_phone': int(bool(tel)), 'has_tech': int(any(x['is_tech'] for x in lpr)),
        'has_purchaser': int(any(x['is_purchaser'] for x in lpr)),
        'flag_mob': int(bool(c.get('lpr_mobilnyy'))), 'flag_fio': int(bool(c.get('lpr_s_fio'))),
        'nazv': c.get('predpriyatie') or '',
    }


def poschitat_vse(kat_put, cat, sales):
    k = sqlite3.connect('file:%s?mode=ro' % kat_put, uri=True)
    k.row_factory = sqlite3.Row
    kompanii = [dict(r) for r in k.execute('SELECT * FROM company')]
    k.close()
    return {c['inn']: razbor_kompanii(c, cat.contacts(c['inn']), cat, sales) for c in kompanii}


# ====================================================================== показатели качества
def mediana(v):
    v = sorted(x for x in v if x is not None)
    if not v:
        return 0
    n = len(v)
    return v[n // 2] if n % 2 else (v[n // 2 - 1] + v[n // 2]) / 2


POKAZATELI = [
    ('t4', 'ЛПР с ФИО и мобильным (ступень 800)', lambda r: int(r['tier'] == 4)),
    ('t3', 'ЛПР с мобильным без ФИО (600)', lambda r: int(r['tier'] == 3)),
    ('t2', 'ЛПР с рабочим/добавочным (400)', lambda r: int(r['tier'] == 2)),
    ('t1', 'без ЛПР (200)', lambda r: int(r['tier'] == 1)),
    ('t0', 'пометка очереди (0, в конце)', lambda r: r['pometka']),
    ('lpr_mob_vse', 'ЛПР с мобильным, всего (800+600)', lambda r: int(r['tier'] in (3, 4))),
    ('lpr_fio', 'ЛПР с ФИО', lambda r: r['lpr_fio']),
    ('tech', 'тех. ЛПР', lambda r: r['tech']),
    ('klient_sc', 'клиенты СЦ', lambda r: r['klient_sc']),
    ('bitrix', 'есть сделки в Битриксе', lambda r: r['bitrix']),
] + [('baza%s' % b[-1], 'в базе: %s' % b, (lambda bb: (lambda r: int(bb in r['bazy'])))(b)) for b in BAZY]


def tablica(raspr, dannye, zagolovok):
    """raspr: ИНН -> продавец. -> текст таблицы и словарь чисел."""
    po = {p: [dannye[i] for i, u in raspr.items() if u == p and i in dannye] for p in PRODAVCY}
    chisla = {}
    stroki = ['%s' % zagolovok, '%-40s %s %s' % ('', ' '.join('%8s' % p for p in PRODAVCY), '  разница')]
    stroki.append('%-40s %s' % ('компаний', ' '.join('%8d' % len(po[p]) for p in PRODAVCY)))
    for kl, nazv, f in POKAZATELI:
        v = [sum(f(r) for r in po[p]) for p in PRODAVCY]
        chisla[kl] = v
        stroki.append('%-40s %s %8d' % (nazv[:40], ' '.join('%8d' % x for x in v), max(v) - min(v)))
    med = [mediana([r['vyr'] for r in po[p]]) / 1e6 for p in PRODAVCY]
    chisla['mediana'] = med
    stroki.append('%-40s %s %8.0f' % ('медиана выручки, млн', ' '.join('%8.0f' % x for x in med), max(med) - min(med)))
    sr = [sum(r['ball'] for r in po[p]) / max(1, len(po[p])) for p in PRODAVCY]
    chisla['ball_sr'] = sr
    stroki.append('%-40s %s %8.1f' % ('средняя важность (без ступени)', ' '.join('%8.1f' % x for x in sr), max(sr) - min(sr)))
    sc = [sum(r['score'] for r in po[p]) / max(1, len(po[p])) for p in PRODAVCY]
    chisla['score_sr'] = sc
    stroki.append('%-40s %s %8.1f' % ('средний балл очереди', ' '.join('%8.1f' % x for x in sc), max(sc) - min(sc)))
    return '\n'.join(stroki), chisla


# ====================================================================== единицы раздачи
def edinicy_razdachi(hold, vse_inn):
    """Группы fixD + пары с общими номерами -> связные компоненты (только ИНН панели)."""
    rod = {}

    def koren(a):
        rod.setdefault(a, a)
        while rod[a] != a:
            rod[a] = rod[rod[a]]
            a = rod[a]
        return a

    def soed(a, b):
        rod[koren(a)] = koren(b)
    po_gr = collections.defaultdict(list)
    for inn, g in hold['inn_gruppa'].items():
        if inn in vse_inn:
            po_gr[g].append(inn)
    pochemu = collections.defaultdict(set)
    for g, inns in po_gr.items():
        for i in inns:
            koren(i)
            pochemu[i].add('холдинг %s' % hold['gruppy'][g]['nazvanie'])
        for i in inns[1:]:
            soed(inns[0], i)
    for p in hold['obshchie_nomera_bez_svyazi']:
        inns = [i for i in p['inns'] if i in vse_inn]
        for i in inns:
            koren(i)
            pochemu[i].add('общий номер без доказанной связи: %s' % ' / '.join(p['nazvaniya']))
        for i in inns[1:]:
            soed(inns[0], i)
    komp = collections.defaultdict(list)
    for i in list(rod):
        komp[koren(i)].append(i)
    for i in vse_inn:
        if i not in rod:
            komp['one-' + i].append(i)
    return {('u-' + min(v)): sorted(v) for v in komp.values()}, pochemu


# ====================================================================== ЛОКАЛЬНЫЙ ПЛАН
def plan_lokalno(kat_put, sales_put, koren_app, hold_put, vyhod):
    os.environ['CENTRIFUGAL_DB'] = kat_put
    os.environ['CENTRO_DB'] = kat_put
    os.environ['CENTRO_SALES_DB'] = sales_put
    sys.path.insert(0, koren_app)
    from app.services import centro_catalog as cat
    from app.services import centro_sales as sales
    import numpy as np
    from scipy.optimize import Bounds, LinearConstraint, milp

    dannye = poschitat_vse(kat_put, cat, sales)
    s = sqlite3.connect('file:%s?mode=ro' % sales_put, uri=True)
    vlad = dict(s.execute('SELECT inn, username FROM company_assignment').fetchall())
    zakrep = set()
    for t in ('company_state', 'company_comment', 'zvonok_sobytie', 'activity_log'):
        try:
            zakrep |= {str(r[0]) for r in s.execute('SELECT DISTINCT inn FROM %s WHERE inn IS NOT NULL' % t)}
        except sqlite3.OperationalError:
            pass
    s.close()
    hold = json.load(io.open(hold_put, encoding='utf-8'))
    vse = sorted(i for i in vlad if i in dannye)
    edin, pochemu_ed = edinicy_razdachi(hold, set(vse))
    U = sorted(edin)
    P = PRODAVCY
    # допустимые продавцы единицы: закреплённые (есть действия) – только свой; группа – тот,
    # у кого больше её членов (при равенстве – любой из них); одиночка – любой
    dop = {}
    konflikty = []
    for u in list(U):
        chl = edin[u]
        zak = {vlad[i] for i in chl if i in zakrep}
        if len(zak) > 1:
            # действия по группе у двух продавцов: работу не отнимаем, группу не сводим
            konflikty.append({'gruppa': chl, 'prodavcy': sorted(zak)})
            U.remove(u)
            del edin[u]
            for i in chl:
                edin['k-' + i] = [i]
                U.append('k-' + i)
                dop['k-' + i] = [vlad[i]] if i in zakrep else list(P)
            continue
        if zak:
            dop[u] = sorted(zak)[:1]
        elif len(chl) > 1:
            sch = collections.Counter(vlad[i] for i in chl)
            m = max(sch.values())
            dop[u] = sorted(p for p, n in sch.items() if n == m)
        else:
            dop[u] = list(P)
    # переменные x[u,p]
    idx = {}
    for u in U:
        for p in dop[u]:
            idx[(u, p)] = len(idx)
    nx = len(idx)
    metriki = [(kl, f) for kl, _, f in POKAZATELI if kl not in ('lpr_mob_vse',)]
    # выручка: поровну компаний без выручки и поровну НИЖЕ каждого порога (накопительно) –
    # тогда медиана у каждого продавца встаёт рядом с общей медианой
    vy = sorted(dannye[i]['vyr'] for i in vse if dannye[i]['vyr'])
    porogi = [vy[int(len(vy) * q)] for q in (0.25, 0.4, 0.46, 0.48, 0.5, 0.52, 0.54, 0.6, 0.75)]
    metriki.append(('vyr_net', lambda r: int(not r['vyr'])))
    for n_t, t in enumerate(porogi):
        metriki.append(('vyr_nizhe%d' % n_t, (lambda tt: (lambda r: int(bool(r['vyr']) and r['vyr'] < tt)))(t)))
    # стоимость: перемещённые компании
    cost = np.zeros(nx)
    for (u, p), j in idx.items():
        cost[j] = sum(1 for i in edin[u] if vlad[i] != p)
    A, lo, hi = [], [], []
    # каждая единица – ровно одному
    for u in U:
        row = np.zeros(nx)
        for p in dop[u]:
            row[idx[(u, p)]] = 1
        A.append(row); lo.append(1); hi.append(1)
    # ровно 150
    for p in P:
        row = np.zeros(nx)
        for u in U:
            if (u, p) in idx:
                row[idx[(u, p)]] = len(edin[u])
        A.append(row); lo.append(len(vse) // 4); hi.append(len(vse) // 4)
    # показатели: floor/ceil(N/4) +- допуск (допуск 0 -> разница <= 1)
    dopusk = {}
    for kl, f in metriki:
        N = sum(f(dannye[i]) for i in vse)
        dopusk[kl] = N
    rezultat = None
    for zapas in (0, 1):
        A2, lo2, hi2 = list(A), list(lo), list(hi)
        for kl, f in metriki:
            N = dopusk[kl]
            for p in P:
                row = np.zeros(nx)
                for u in U:
                    if (u, p) in idx:
                        row[idx[(u, p)]] = sum(f(dannye[i]) for i in edin[u])
                A2.append(row); lo2.append(N // 4 - zapas); hi2.append(-(-N // 4) + zapas)
        res = milp(cost, constraints=LinearConstraint(np.array(A2), lo2, hi2),
                   integrality=np.ones(nx), bounds=Bounds(0, 1), options={'time_limit': 300})
        print('MILP запас %d: %s, перемещений %s' % (zapas, res.message, res.fun))
        if res.x is not None and res.status in (0, 1):
            rezultat = res
            break
    if rezultat is None:
        raise SystemExit('план не найден')
    novoe = {}
    for (u, p), j in idx.items():
        if rezultat.x[j] > 0.5:
            for i in edin[u]:
                novoe[i] = p
    peremeshcheniya = []
    for i in vse:
        if novoe[i] != vlad[i]:
            u = next(uu for uu in U if i in edin[uu])
            if len(edin[u]) > 1:
                prich = ('холдинг целиком одному продавцу (%s)' % '; '.join(sorted(pochemu_ed[i]))[:300])
                if len({vlad[x] for x in edin[u]}) == 1:
                    prich = 'выравнивание очередей по качеству (группа целиком): ' + '; '.join(sorted(pochemu_ed[i]))[:250]
            else:
                prich = 'выравнивание очередей по качеству'
            peremeshcheniya.append({'inn': i, 'ot': vlad[i], 'komu': novoe[i], 'prichina': prich,
                                    'nazvanie': dannye[i]['nazv'], 'stupen': STUPEN[dannye[i]['tier']]})
    t_do, ch_do = tablica(vlad, dannye, 'ДО (нынешняя раздача, новые ступени и флаги)')
    t_po, ch_po = tablica(novoe, dannye, 'ПОСЛЕ')
    print(t_do)
    print(t_po)
    print('перемещений: %d; закреплённых (есть действия): %d; конфликтов закрепления в группах: %d'
          % (len(peremeshcheniya), len(zakrep), len(konflikty)))
    # проверка групп
    for u in U:
        if len({novoe[i] for i in edin[u]}) != 1:
            raise SystemExit('группа разорвана: %s' % edin[u])
    plan = {'vremya': time.strftime('%Y%m%d-%H%M%S'), 'vladelcy_do': vlad, 'vladelcy_posle': novoe,
            'peremeshcheniya': peremeshcheniya, 'zakrep_pri_plane': sorted(zakrep),
            'edinicy': {u: v for u, v in edin.items() if len(v) > 1}, 'konflikty': konflikty,
            'ball': {i: {k: dannye[i][k] for k in ('tier', 'ball', 'score', 'pochemu')} for i in dannye},
            'tablica_do': t_do, 'tablica_posle': t_po, 'chisla_do': ch_do, 'chisla_posle': ch_po}
    io.open(vyhod, 'w', encoding='utf-8').write(json.dumps(plan, ensure_ascii=False, indent=1))
    print('план: %s' % vyhod)


# ====================================================================== СЕРВЕР
VENV = r'C:\seostat\.venv\Scripts\python.exe'
KOREN = r'C:\centro2'
KAT = os.path.join(KOREN, 'data', 'meyer_baza1.db')
SALES = os.path.join(KOREN, 'data', 'centro_sales_meyer1.db')
DROP = r'C:\seostat\drop\drop-storage'
PLAN_PUT = os.path.join(DROP, 'fixE2-plan.json')
PUT = '/obzvon-meyer'
DEYSTVIYA = ('company_state', 'company_comment', 'zvonok_sobytie', 'activity_log')


def kopiya(src_put, dst_put):
    src = sqlite3.connect('file:%s?mode=ro' % src_put, uri=True)
    dst = sqlite3.connect(dst_put)
    src.backup(dst)
    dst.close()
    src.close()


def zakreplennye(conn):
    z = set()
    for t in DEYSTVIYA:
        try:
            z |= {str(r[0]) for r in conn.execute('SELECT DISTINCT inn FROM %s WHERE inn IS NOT NULL' % t)}
        except sqlite3.OperationalError:
            pass
    return z


def primenit(suhoy, tolko_ball, KAT=KAT, SALES=SALES, metka=''):
    sys.path.insert(0, KOREN)
    import zapusk  # noqa: F401  – .env в окружение
    import logging
    logging.disable(logging.CRITICAL)
    if metka:                                   # репетиция на копиях баз
        for kk in ('CENTRO_SALES_DB', 'PARK_OCHERED_SALES_DB'):
            os.environ[kk] = SALES
        for kk in ('CENTRIFUGAL_DB', 'CENTRO_DB', 'PARK_OCHERED_DB'):
            os.environ[kk] = KAT
    assert os.path.normcase(os.environ.get('CENTRIFUGAL_DB', '')) == os.path.normcase(KAT)
    assert os.path.normcase(os.environ.get('CENTRO_SALES_DB', '')) == os.path.normcase(SALES)
    from app.services import centro_catalog as cat
    from app.services import centro_sales as sales
    VREMYA = time.strftime('%Y%m%d-%H%M%S')
    plan = None if tolko_ball else json.load(io.open(PLAN_PUT, encoding='utf-8'))
    # ---------- 0. копии баз (НЕ для отката целиком)
    BEKAP = os.path.join(KOREN, '_bekap', 'fixE2-' + VREMYA + metka)
    os.makedirs(BEKAP, exist_ok=True)
    if not metka:
        kopiya(KAT, os.path.join(BEKAP, 'meyer_baza1.db'))
        kopiya(SALES, os.path.join(BEKAP, 'centro_sales_meyer1.db'))
    print('копии баз: %s%s' % (BEKAP, ' (репетиция на копиях)' if metka else ''))
    # ---------- 1. балл на живом каталоге
    dannye = poschitat_vse(KAT, cat, sales)
    if plan:
        rash = [(i, plan['ball'][i]['tier'], dannye[i]['tier']) for i in dannye
                if i in plan['ball'] and plan['ball'][i]['tier'] != dannye[i]['tier']]
        print('ступень на живом каталоге отличается от плана у %d: %s' % (len(rash), rash[:10]))
    # ---------- 2. проверки на живой базе продаж (под записью – BEGIN IMMEDIATE)
    s = sqlite3.connect(SALES, timeout=30)
    s.row_factory = sqlite3.Row
    s.execute('PRAGMA busy_timeout=30000')
    kol = {r[1] for r in s.execute('PRAGMA table_info(company_assignment)')}
    for imya, tip in (('stupen_ocheredi', 'INTEGER'), ('ball_do_fixE2', 'REAL'), ('vladelec_do_fixE2', 'TEXT')):
        if imya not in kol and not suhoy:
            s.execute('ALTER TABLE company_assignment ADD COLUMN %s %s' % (imya, tip))
            print('добавлена колонка company_assignment.%s' % imya)
    s.commit()
    zhurnal = {'vremya': VREMYA, 'suhoy': suhoy, 'bekap': BEKAP, 'peremeshcheniya': [], 'ball': [], 'katalog': []}
    seychas = sales.utcnow()
    for popytka in range(10):
        try:
            s.execute('BEGIN IMMEDIATE')
            break
        except sqlite3.OperationalError:
            time.sleep(3)
    else:
        raise SystemExit('база продаж занята')
    try:
        stroki = {r['inn']: dict(r) for r in s.execute('SELECT * FROM company_assignment')}
        vlad = {i: r['username'] for i, r in stroki.items()}
        zakrep = zakreplennye(s)
        print('компаний с действиями продавцов (закреплены): %d' % len(zakrep))
        novoe = dict(vlad)
        oshibki = []
        if plan:
            if set(vlad) != set(plan['vladelcy_do']):
                oshibki.append('набор ИНН в назначениях изменился после плана')
            for m in plan['peremeshcheniya']:
                if vlad.get(m['inn']) != m['ot']:
                    oshibki.append('%s: сейчас у %s, а план брал от %s' % (m['inn'], vlad.get(m['inn']), m['ot']))
                elif m['inn'] in zakrep:
                    oshibki.append('%s: по компании уже есть действия – не переносится' % m['inn'])
                novoe[m['inn']] = m['komu']
            sch = collections.Counter(novoe.values())
            if any(sch[p] != 150 for p in PRODAVCY):
                oshibki.append('не по 150: %s' % dict(sch))
            for u, chl in plan['edinicy'].items():
                if len({novoe[i] for i in chl if i in novoe}) > 1:
                    oshibki.append('группа у разных продавцов: %s' % chl)
        if oshibki:
            s.rollback()
            print('ОСТАНОВКА, ничего не записано: %d расхождений, напр. %s' % (len(oshibki), oshibki[:8]))
            raise SystemExit(4)
        # 2а. перемещения
        if plan:
            for m in plan['peremeshcheniya']:
                cur = s.execute(
                    'UPDATE company_assignment SET username=?, assigned_at=?, assigned_by=?, '
                    'vladelec_do_fixE2=COALESCE(vladelec_do_fixE2, ?) WHERE inn=? AND username=?',
                    (m['komu'], seychas, ('fixE2 08.10: ' + m['prichina'])[:200], m['ot'], m['inn'], m['ot']))
                if cur.rowcount != 1:
                    raise RuntimeError('перемещение не записалось: %s' % m['inn'])
                zhurnal['peremeshcheniya'].append({'inn': m['inn'], 'nazvanie': m['nazvanie'], 'ot': m['ot'],
                                                   'komu': m['komu'], 'prichina': m['prichina'],
                                                   'assigned_at_bylo': stroki[m['inn']]['assigned_at'],
                                                   'assigned_by_bylo': stroki[m['inn']]['assigned_by']})
        # 2б. балл очереди и ступень у всех
        for i, r in stroki.items():
            d = dannye.get(i)
            if not d:
                continue
            s.execute('UPDATE company_assignment SET assignment_score=?, stupen_ocheredi=?, has_phone=?, '
                      'has_purchaser=?, has_tech=?, ball_do_fixE2=COALESCE(ball_do_fixE2, ?) WHERE inn=?',
                      (d['score'], d['tier'], d['has_phone'], d['has_purchaser'], d['has_tech'],
                       r['assignment_score'], i))
            zhurnal['ball'].append({'inn': i, 'bylo': [r['assignment_score'], r['has_phone'], r['has_purchaser'], r['has_tech']],
                                    'stalo': [d['score'], d['has_phone'], d['has_purchaser'], d['has_tech']],
                                    'stupen': d['tier']})
        # контроль внутри транзакции
        sch = collections.Counter(r[0] for r in s.execute('SELECT username FROM company_assignment'))
        if not tolko_ball and any(sch[p] != 150 for p in PRODAVCY):
            raise RuntimeError('после записи не по 150: %s' % dict(sch))
        if zakreplennye(s) != zakrep:
            raise RuntimeError('действия продавцов изменились во время записи')
        if suhoy:
            s.rollback()
            print('СУХОЙ ПРОГОН: база продаж не изменена')
        else:
            s.commit()
            print('база продаж: перемещено %d, балл очереди обновлён у %d' % (len(zhurnal['peremeshcheniya']), len(zhurnal['ball'])))
    except BaseException:
        s.rollback()
        raise
    finally:
        s.close()
    # ---------- 3. каталог: важность и расшифровка (прежние – в *_ishodnyy)
    k = sqlite3.connect(KAT, timeout=30)
    k.row_factory = sqlite3.Row
    k.execute('PRAGMA busy_timeout=30000')
    kolk = {r[1] for r in k.execute('PRAGMA table_info(company)')}
    if not suhoy:
        for imya, tip in (('moy_prioritet_ishodnyy', 'REAL'), ('prioritet_pochemu_ishodnyy', 'TEXT')):
            if imya not in kolk:
                k.execute('ALTER TABLE company ADD COLUMN %s %s' % (imya, tip))
        k.commit()
    k.execute('BEGIN IMMEDIATE')
    try:
        for r in k.execute('SELECT inn, moy_prioritet, prioritet_pochemu FROM company').fetchall():
            d = dannye.get(r['inn'])
            if not d:
                continue
            if not suhoy:
                k.execute('UPDATE company SET moy_prioritet_ishodnyy=COALESCE(moy_prioritet_ishodnyy, moy_prioritet), '
                          'prioritet_pochemu_ishodnyy=COALESCE(prioritet_pochemu_ishodnyy, prioritet_pochemu), '
                          'moy_prioritet=?, prioritet_pochemu=? WHERE inn=?', (d['ball'], d['pochemu'], r['inn']))
            zhurnal['katalog'].append({'inn': r['inn'], 'bylo': [r['moy_prioritet'], r['prioritet_pochemu']],
                                       'stalo': [d['ball'], d['pochemu']]})
        if suhoy:
            k.rollback()
        else:
            k.commit()
    except BaseException:
        k.rollback()
        raise
    finally:
        k.close()
    # ---------- 4. журналы на дроп
    hv = ('' if not suhoy else '-suhoy') + metka
    put_zh = os.path.join(DROP, 'fixE2-zhurnal-%s%s.json' % (VREMYA, hv))
    io.open(put_zh, 'w', encoding='utf-8').write(json.dumps(zhurnal, ensure_ascii=False, indent=1))
    put_csv = os.path.join(DROP, 'fixE2-peremeshcheniya-%s%s.csv' % (VREMYA, hv))
    with io.open(put_csv, 'w', encoding='utf-8-sig', newline='') as f:
        f.write('ИНН;Компания;От;Кому;Причина\n')
        for m in zhurnal['peremeshcheniya']:
            f.write('%s;%s;%s;%s;%s\n' % (m['inn'], m['nazvanie'].replace(';', ','), m['ot'], m['komu'],
                                          m['prichina'].replace(';', ',')))
    print('журнал: %s; перемещения: %s' % (put_zh, put_csv))
    # ---------- 5. таблица качества по живым данным
    t_po, ch_po = tablica(novoe if not suhoy else vlad, dannye, 'ПОСЛЕ (живые данные)' if not suhoy else 'СЕЙЧАС')
    print(t_po)
    io.open(os.path.join(DROP, 'fixE2-kachestvo-%s%s.txt' % (VREMYA, hv)), 'w', encoding='utf-8').write(
        (plan['tablica_do'] + '\n\n' if plan else '') + t_po)
    return BEKAP


# ====================================================================== ПРОВЕРКА (venv, копии баз)
def proverka(test_sales, test_kat):
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
    from app.services import centro_catalog as catalog
    from app.services import centro_sales as sales
    from app.obzvon import create_app
    from fastapi.testclient import TestClient
    plohih = [0]

    def ok(u, t):
        if not u:
            plohih[0] += 1
        print('   %s %s' % ('ОК ' if u else 'ПЛОХО', t))
        sys.stdout.flush()
    ok(str(catalog.db_path()) == test_kat and str(sales.sales_db_path()) == test_sales, 'базы – временные копии')
    vnutr = next(z for z in vars(create_app()).values() if hasattr(z, 'routes') and hasattr(z, 'dependency_overrides'))
    ADMIN = {'id': 0, 'username': 'meyer_admin', 'role': 'admin', 'is_active': 1}
    kto = {'u': ADMIN}
    vnutr.dependency_overrides[rcs.current_user] = lambda: kto['u']
    vnutr.dependency_overrides[rcs._same_origin] = lambda: None
    b = sqlite3.connect(test_sales)
    b.row_factory = sqlite3.Row
    kat = sqlite3.connect(test_kat)
    kat.row_factory = sqlite3.Row
    pom = {r[0] for r in kat.execute("SELECT inn FROM company WHERE TRIM(COALESCE(pometka_ocheredi,''))<>''")}
    vlad = dict(b.execute('SELECT inn, username FROM company_assignment').fetchall())
    stup = dict(b.execute('SELECT inn, stupen_ocheredi FROM company_assignment').fetchall())
    sch = collections.Counter(vlad.values())
    ok(all(sch[p] == 150 for p in PRODAVCY), 'по 150 у каждого: %s' % dict(sch))
    hold = json.load(io.open(os.path.join(DROP, 'fixD-holdingi.json'), encoding='utf-8'))
    edin, _ = edinicy_razdachi(hold, set(vlad))
    razorv = [v for v in edin.values() if len({vlad[i] for i in v}) > 1]
    ok(not razorv, 'каждая группа холдинга и пара с общими номерами – у одного продавца (%d групп)%s'
       % (sum(1 for v in edin.values() if len(v) > 1), (': разорваны %s' % razorv[:3]) if razorv else ''))
    rx_row = re.compile(r'<tr data-href="[^"]*centro\?inn=(\d+)[^"]*">.*?class="chislo tiho och-ball"[^>]*>([-\d.]+)</td>', re.S)
    with TestClient(vnutr) as kl:
        def poluchit(u, kak=ADMIN, **kw):
            kto['u'] = kak
            return kl.get(PUT + u, **kw)
        for nazv, u in (('главная', '/centro'), ('статистика', '/centro/stats'), ('CSV', '/centro/vygruzka.csv')):
            o = poluchit(u)
            ok(o.status_code == 200, 'админ, %s: %s' % (nazv, o.status_code))
        for n_p, p in enumerate(PRODAVCY, 1):
            PROD = {'id': n_p, 'username': p, 'role': 'sales', 'is_active': 1}
            stroki = []
            for st in (1, 2):
                o = poluchit('/centro', PROD, params={'size': 100, 'page': st})
                ok(o.status_code == 200, '%s: список, стр. %d: %s' % (p, st, o.status_code))
                stroki += [(i, float(v)) for i, v in rx_row.findall(o.text)]
            novyh = sum(1 for i in vlad if vlad[i] == p)
            ok(len(stroki) == len({i for i, _ in stroki}), '%s: строк в списке %d (уникальных)' % (p, len(stroki)))
            bally = [v for _, v in stroki]
            ok(all(bally[j] >= bally[j + 1] for j in range(len(bally) - 1)),
               '%s: числа «Балл очереди» идут по убыванию сверху вниз (%s … %s)' % (p, bally[:3], bally[-2:]))
            top = [stup.get(i) for i, _ in stroki[:20]]
            ok(all(t in (2, 3, 4) for t in top), '%s: топ-20 – только компании с ЛПР с телефоном (ступени %s)'
               % (p, collections.Counter(top)))
            konec = [i for i, _ in stroki][-sum(1 for i, _ in stroki if i in pom):] if any(i in pom for i, _ in stroki) else []
            ok(all(i in pom for i in konec) and len(konec) == sum(1 for i in vlad if vlad[i] == p and i in pom),
               '%s: компании с пометкой – в самом конце (%d)' % (p, len(konec)))
            t_ = [stup.get(i) for i, _ in stroki]
            ok(all((t_[j] or 0) >= (t_[j + 1] or 0) for j in range(len(t_) - 1)), '%s: ступени не возрастают вниз по списку' % p)
            o = poluchit('/centro', PROD, params={'inn': stroki[0][0]})
            ok(o.status_code == 200 and 'Балл очереди' in o.text, '%s: карточка №1 %s: %s' % (p, stroki[0][0], o.status_code))
            o = poluchit('/centro/stats', PROD)
            ok(o.status_code == 403, '%s: статистика продавцу закрыта: %s' % (p, o.status_code))
            # CSV директора по этому продавцу – тот же порядок
            o = poluchit('/centro/vygruzka.csv', params={'assigned_user': p})
            import csv as _csv
            csv_inn = [r[2] for r in list(_csv.reader(io.StringIO(o.content.decode('utf-8-sig')), delimiter=';'))[1:] if len(r) > 5]
            ok(csv_inn == [i for i, _ in stroki], '%s: CSV в том же порядке, что список (%d строк)' % (p, len(csv_inn)))
            # статистика директора: очередь продавца – тот же порядок
            o = poluchit('/centro/stats', params={'user': p})
            st_inn = re.findall(r'<td>(\d{10,12})</td>\s*<td>[-\d.]+</td>', o.text)
            ok(o.status_code == 200 and st_inn[:len(stroki)] == [i for i, _ in stroki],
               'статистика, очередь %s: %s, тот же порядок (%d строк)' % (p, o.status_code, len(st_inn)))
            print('   %s: топ-20 %s' % (p, ' '.join('%s(%d)' % (i[-4:], stup.get(i) or 0) for i, _ in stroki[:20])))
            print('   %s: хвост %s' % (p, ' '.join('%s(%s)' % (i[-4:], 'П' if i in pom else stup.get(i)) for i, _ in stroki[-5:])))
    print('ПЛОХИХ ПРОВЕРОК: %d' % plohih[0])
    return plohih[0]


if __name__ == '__main__' and '--plan' in sys.argv:
    i = sys.argv.index('--plan')
    plan_lokalno(*sys.argv[i + 1:i + 6])
elif __name__ == '__main__' and '--proverka' in sys.argv:
    i = sys.argv.index('--proverka')
    raise SystemExit(1 if proverka(sys.argv[i + 1], sys.argv[i + 2]) else 0)
elif __name__ == '__main__' and '--vnutri' in sys.argv:
    if '--na-kopii' in sys.argv:
        # РЕПЕТИЦИЯ: всё то же самое на свежих копиях боевых баз, боевые не трогаются
        papka = os.path.join(KOREN, '_bekap', 'fixE2-repeticiya-' + time.strftime('%Y%m%d-%H%M%S'))
        os.makedirs(papka, exist_ok=True)
        ts, tk = os.path.join(papka, 'test_sales.db'), os.path.join(papka, 'test_kat.db')
        kopiya(SALES, ts)
        kopiya(KAT, tk)
        bekap = primenit(False, '--tolko-ball' in sys.argv, KAT=tk, SALES=ts, metka='-kopiya')
    else:
        bekap = primenit('--suhoy' in sys.argv, '--tolko-ball' in sys.argv)
    if '--suhoy' not in sys.argv:
        if '--na-kopii' not in sys.argv:
            ts, tk = os.path.join(bekap, 'test_sales.db'), os.path.join(bekap, 'test_kat.db')
            kopiya(SALES, ts)
            kopiya(KAT, tk)
        r = subprocess.run([VENV, os.path.abspath(__file__), '--proverka', ts, tk], capture_output=True,
                           timeout=900, cwd=KOREN, env=dict(os.environ, PYTHONIOENCODING='utf-8'))
        vyvod = r.stdout.decode('utf-8', 'replace') + r.stderr.decode('utf-8', 'replace')[-3000:]
        io.open(os.path.join(DROP, 'fixE2-proverka-%s.txt' % os.path.basename(bekap)), 'w', encoding='utf-8').write(vyvod)
        print('===== ПРОВЕРКА (на копиях баз после записи) =====')
        print(vyvod[-3500:])
        for t in (ts, tk):
            try:
                os.remove(t)
            except OSError:
                pass
elif __name__ == '__main__' and '--tolko-proverka' in sys.argv:
    # только чтение: свежие копии боевых баз -> та же проверка (venv)
    papka = os.path.join(KOREN, '_bekap', 'fixE2-proverka-' + time.strftime('%Y%m%d-%H%M%S'))
    os.makedirs(papka, exist_ok=True)
    ts, tk = os.path.join(papka, 'test_sales.db'), os.path.join(papka, 'test_kat.db')
    kopiya(SALES, ts)
    kopiya(KAT, tk)
    r = subprocess.run([VENV, os.path.abspath(__file__), '--proverka', ts, tk], capture_output=True,
                       timeout=900, cwd=KOREN, env=dict(os.environ, PYTHONIOENCODING='utf-8'))
    vyvod = r.stdout.decode('utf-8', 'replace') + r.stderr.decode('utf-8', 'replace')[-3000:]
    io.open(os.path.join(DROP, 'fixE2-proverka-%s.txt' % os.path.basename(papka)), 'w', encoding='utf-8').write(vyvod)
    for t in (ts, tk):
        try:
            os.remove(t)
        except OSError:
            pass
    sys.stdout.write(vyvod[-5500:])
elif __name__ == '__main__' and ('--primenit' in sys.argv or '--tolko-ball' in sys.argv or '--na-kopii' in sys.argv):
    r = subprocess.run([VENV, os.path.abspath(__file__), '--vnutri'] + sys.argv[1:], capture_output=True,
                       timeout=1650, cwd=KOREN, env=dict(os.environ, PYTHONIOENCODING='utf-8'))
    sys.stdout.write(r.stdout.decode('utf-8', 'replace')[-5900:])
    if r.returncode:
        sys.stdout.write('\n--- stderr ---\n' + r.stderr.decode('utf-8', 'replace')[-2500:])
    raise SystemExit(r.returncode)
