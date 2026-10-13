# -*- coding: utf-8 -*-
"""fixI (локально): правило владельца 13.10 «у кого какой город – другим этот город не отдавать (область/край)».

Города: Пяткова, Волков – Барнаул; Ерохин, Беляев – Краснодар (новые meyer5–9 – 0 компаний, им отдельная база).
Значит: Алтайский край – только Пятковой/Волкову, Краснодарский край – только Ерохину/Беляеву (поровну, как было),
Воронежская область – никому из четырёх (её в каталоге нет); прочие регионы – любому. Республика Алтай – другой субъект.

Раскладка – MILP fixG2/fixH: единицы – группы холдингов и пары с общими номерами целиком; у каждого ровно 150;
показатели E2 (ступени, «ЛПР с мобильным всего», ЛПР с ФИО, тех. ЛПР, клиенты СЦ, Битрикс, базы, пороги выручки ->
медиана) и клиенты Meyer / «в работе у КЦ/СЦ» – в коридорах, средний балл очереди – в коридоре; цель – минимум
перемещений; компании с действиями продавцов не двигаются. Берётся самый строгий вариант, который стоит не больше
чем на 3 перемещения дороже самого дешёвого.

    python3 fixI_plan.py <папка fixI (db0, kodroot, fixD-holdingi.json)> <выход plan.json>
"""
import collections
import io
import json
import os
import shutil
import sqlite3
import sys
import time

W, OUT = sys.argv[1:3]
ZDES = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ZDES)
SIM = os.path.join(W, 'sim')
os.makedirs(SIM, exist_ok=True)
for f in ('meyer_baza1.db', 'centro_sales_meyer1.db'):
    shutil.copy(os.path.join(W, 'db0', f), os.path.join(SIM, f))
os.environ['CENTRIFUGAL_DB'] = os.environ['CENTRO_DB'] = os.path.join(SIM, 'meyer_baza1.db')
os.environ['CENTRO_SALES_DB'] = os.path.join(SIM, 'centro_sales_meyer1.db')
sys.path.insert(0, os.path.join(W, 'kodroot'))
from app.services import centro_catalog as cat  # noqa: E402
from app.services import centro_sales as sales  # noqa: E402
import fixF2_ball as E2  # noqa: E402
import numpy as np  # noqa: E402
from scipy.optimize import Bounds, LinearConstraint, milp  # noqa: E402

PRODAVCY = ['meyer1', 'meyer2', 'meyer3', 'meyer4']
assert list(E2.PRODAVCY) == PRODAVCY, E2.PRODAVCY
FIO = {'meyer1': 'Пяткова', 'meyer2': 'Ерохин', 'meyer3': 'Беляев', 'meyer4': 'Волков'}
GOROD = {'meyer1': 'Барнаул', 'meyer2': 'Краснодар', 'meyer3': 'Краснодар', 'meyer4': 'Барнаул'}
# регион -> кому можно (из четырёх); Воронеж – только meyer5/meyer6, у четырёх старых его быть не должно
DOM = {'Алтайский край': ['meyer1', 'meyer4'], 'Краснодарский край': ['meyer2', 'meyer3'], 'Воронежская область': []}
KRD = 'Краснодарский край'

k = sqlite3.connect(os.path.join(SIM, 'meyer_baza1.db'))
k.row_factory = sqlite3.Row
s_ = sqlite3.connect(os.path.join(SIM, 'centro_sales_meyer1.db'))
vlad = dict(s_.execute('SELECT inn, username FROM company_assignment').fetchall())
zakrep = set()
for t in ('company_state', 'company_comment', 'zvonok_sobytie', 'activity_log', 'hidden_item'):
    try:
        zakrep |= {str(r[0]) for r in s_.execute('SELECT DISTINCT inn FROM %s WHERE inn IS NOT NULL' % t)}
    except sqlite3.OperationalError:
        pass
kat = {r['inn']: dict(r) for r in k.execute('SELECT * FROM company')}
region = {i: c['region'] for i, c in kat.items()}
naim = {i: c['predpriyatie'] for i, c in kat.items()}
assert set(vlad) == set(kat) and set(vlad.values()) <= set(PRODAVCY), 'назначения не совпадают с каталогом'
dannye = E2.poschitat_vse(os.path.join(SIM, 'meyer_baza1.db'), cat, sales)
for i in dannye:
    dannye[i]['klient_meyer'] = int(float(kat[i].get('bitrix_klient_meyer') or 0) > 0)
    dannye[i]['v_rabote'] = int(float(kat[i].get('bitrix_v_rabote') or 0) > 0)
vor = [i for i in kat if region[i] == 'Воронежская область']
assert not vor, 'в каталоге есть воронежские: %s' % vor
ne_doma = [i for i in kat if region[i] in DOM and vlad[i] not in DOM[region[i]]]
print('компаний %d; действий продавцов: %d; не у «своего города»: %d' % (len(kat), len(zakrep), len(ne_doma)))
for i in ne_doma:
    print('   %s %-36s %-20s у %s' % (i, naim[i][:36], region[i], FIO[vlad[i]]))

# единицы раздачи: группы fixD + группы каталога gG-…
hold = json.load(open(os.path.join(W, 'fixD-holdingi.json'), encoding='utf-8'))
for g in {r[0] for r in k.execute("SELECT DISTINCT gruppa FROM holding_chlen WHERE gruppa LIKE 'gG-%'")}:
    hold['gruppy'][g] = {'nazvanie': g}
    for r in k.execute('SELECT inn FROM holding_chlen WHERE gruppa=?', (g,)):
        hold['inn_gruppa'][r[0]] = g
vse = sorted(dannye)
edin, pochemu_ed = E2.edinicy_razdachi(hold, set(vse))
U = sorted(edin)
N = len(vse)
CEL = {p: N // 4 + (1 if n < N % 4 else 0) for n, p in enumerate(PRODAVCY)}
krd = {i for i in vse if region[i] == KRD}
K = len(krd)
dop, konflikty, smeshannye = {}, [], []
for u in U:
    chl = edin[u]
    mozhno = set(PRODAVCY)
    for i in chl:
        if region[i] in DOM:
            mozhno &= set(DOM[region[i]])
    if len({region[i] for i in chl}) > 1 and any(region[i] in DOM for i in chl):
        smeshannye.append({'chleny': [(i, naim[i], region[i], FIO[vlad[i]]) for i in chl], 'mozhno': sorted(mozhno)})
    zak = {vlad[i] for i in chl if i in zakrep}
    if zak:
        dop[u] = sorted(zak)[:1]
        if not set(dop[u]) <= mozhno:
            konflikty.append('группа %s с действиями у %s – по правилу городов ей туда нельзя; остаётся' % (chl, dop[u][0]))
    elif not mozhno:
        raise SystemExit('группе %s по правилу городов некому достаться' % chl)
    else:
        dop[u] = sorted(mozhno)
print('единиц раздачи %d (групп из 2+ компаний %d); смешанных групп «домашний регион + другой»: %d %s' % (
    len(U), sum(1 for u in U if len(edin[u]) > 1), len(smeshannye), smeshannye))
idx = {}
for u in U:
    for p in dop[u]:
        idx[(u, p)] = len(idx)
nx = len(idx)
cost = np.zeros(nx)
for (u, p), j in idx.items():
    cost[j] = sum(1 for i in edin[u] if vlad[i] != p)
metriki = [(kl, f) for kl, _, f in E2.POKAZATELI if kl not in ('lpr_mob_vse', 't0')]
metriki.append(('lpr_mob_vse', lambda r: int(r['tier'] in (3, 4))))
metriki.append(('klient_meyer', lambda r: r['klient_meyer']))
metriki.append(('v_rabote', lambda r: r['v_rabote']))
vy = sorted(dannye[i]['vyr'] for i in vse if dannye[i]['vyr'])
porogi = [vy[int(len(vy) * q)] for q in (0.25, 0.4, 0.46, 0.48, 0.5, 0.52, 0.54, 0.6, 0.75)]
metriki.append(('vyr_net', lambda r: int(not r['vyr'])))
for n_t, t in enumerate(porogi):
    metriki.append(('vyr_nizhe%d' % n_t, (lambda tt: (lambda r: int(bool(r['vyr']) and r['vyr'] < tt)))(t)))
STUPENI = {'t4', 't3', 't2', 't1', 'lpr_mob_vse'}


def polosa(tot, w):
    if w <= 1:
        return tot // 4, -(-tot // 4)
    lo = -(-tot // 4) - (w // 2)
    return lo, lo + w


def reshit(zapas_stup, zapas_proch, koridor):
    A, lo, hi = [], [], []
    for u in U:
        row = np.zeros(nx)
        for p in dop[u]:
            row[idx[(u, p)]] = 1
        A.append(row); lo.append(1); hi.append(1)
    for p in PRODAVCY:
        row = np.zeros(nx)
        for u in U:
            if (u, p) in idx:
                row[idx[(u, p)]] = len(edin[u])
        A.append(row); lo.append(CEL[p]); hi.append(CEL[p])
    for p in DOM[KRD]:                          # краснодарские у Ерохина и Беляева – поровну (как было)
        row = np.zeros(nx)
        for u in U:
            if (u, p) in idx:
                row[idx[(u, p)]] = sum(1 for i in edin[u] if i in krd)
        A.append(row); lo.append(K // 2); hi.append(-(-K // 2))
    for kl, f in metriki:
        tot = sum(f(dannye[i]) for i in vse)
        a, b = polosa(tot, zapas_stup if kl in STUPENI else zapas_proch)
        for p in PRODAVCY:
            row = np.zeros(nx)
            for u in U:
                if (u, p) in idx:
                    row[idx[(u, p)]] = sum(f(dannye[i]) for i in edin[u])
            A.append(row); lo.append(a); hi.append(b)
    sr = sum(dannye[i]['score'] for i in vse) / N
    for p in PRODAVCY:
        row = np.zeros(nx)
        for u in U:
            if (u, p) in idx:
                row[idx[(u, p)]] = sum(dannye[i]['score'] for i in edin[u])
        A.append(row); lo.append((sr - koridor) * CEL[p]); hi.append((sr + koridor) * CEL[p])
    return milp(cost, constraints=LinearConstraint(np.array(A), lo, hi), integrality=np.ones(nx),
                bounds=Bounds(0, 1), options={'time_limit': 240})


VARIANTY = [(1, 1, 2), (1, 2, 3), (1, 3, 3), (2, 2, 3), (2, 3, 5)]
reshennye = []
for zs, zp, kor in VARIANTY:
    res = reshit(zs, zp, kor)
    ok_ = res.x is not None and res.status in (0, 1)
    print('MILP: разница ступеней <=%d, прочих <=%d, средний балл ±%d: %s, перемещений %s' % (
        zs, zp, kor, res.message[:40], round(res.fun) if ok_ else '–'))
    if ok_:
        reshennye.append((round(res.fun), VARIANTY.index((zs, zp, kor)), res, zs, zp, kor))
if not reshennye:
    raise SystemExit('раскладка не найдена')
mn = min(x[0] for x in reshennye)
_, _, res, zs, zp, kor = min((x for x in reshennye if x[0] <= mn + 3), key=lambda x: x[1])
print('выбран вариант: ступени <=%d, прочие <=%d, балл ±%d (минимум перемещений среди вариантов – %d)' % (zs, zp, kor, mn))
novoe = {}
for (u, p), j in idx.items():
    if res.x[j] > 0.5:
        for i in edin[u]:
            novoe[i] = p
for u in U:
    assert len({novoe[i] for i in edin[u]}) == 1, edin[u]
peremeshcheniya = []
for i in vse:
    if novoe[i] != vlad[i]:
        u = next(uu for uu in U if i in edin[uu])
        if region[i] in DOM and vlad[i] not in DOM[region[i]]:
            prich = '%s – только продавцам города %s (правило владельца 13.10)' % (region[i], GOROD[DOM[region[i]][0]])
        elif vlad[i] in ('meyer1', 'meyer4') and novoe[i] in ('meyer2', 'meyer3'):
            prich = 'взамен алтайских: от барнаульских к краснодарским, регион не домашний ни для кого (13.10)'
        else:
            prich = 'выравнивание качества очередей при передаче алтайских (13.10)'
        if len(edin[u]) > 1:
            prich += '; группа целиком: ' + '; '.join(sorted(pochemu_ed.get(i, [])))[:200]
        peremeshcheniya.append({'inn': i, 'nazvanie': naim[i], 'region': region[i], 'ot': vlad[i], 'komu': novoe[i],
                                'prichina': prich, 'stupen': E2.STUPEN[dannye[i]['tier']], 'ball': dannye[i]['score'],
                                'vyruchka_mln': round((dannye[i]['vyr'] or 0) / 1e6)})
t_do, ch_do = E2.tablica(vlad, dannye, 'ДО (сейчас)')
t_po, ch_po = E2.tablica(novoe, dannye, 'ПОСЛЕ (правило городов 13.10)')
print(t_do)
print(t_po)
for kl in ('klient_meyer', 'v_rabote'):
    print('%s: до %s, после %s' % (kl, [sum(dannye[i][kl] for i in vse if vlad[i] == p) for p in PRODAVCY],
                                  [sum(dannye[i][kl] for i in vse if novoe[i] == p) for p in PRODAVCY]))
reg_po = {r: dict(collections.Counter(FIO[novoe[i]] for i in vse if region[i] == r)) for r in DOM}
reg_do = {r: dict(collections.Counter(FIO[vlad[i]] for i in vse if region[i] == r)) for r in DOM}
print('по домашним регионам: до %s; после %s' % (reg_do, reg_po))
pot = collections.Counter((m['ot'], m['komu']) for m in peremeshcheniya)
print('перемещений %d: %s' % (len(peremeshcheniya), {'%s→%s' % (FIO[a], FIO[b]): n for (a, b), n in sorted(pot.items())}))
for m in peremeshcheniya:
    print('   %s %-34s %-22s %s → %s · ступень %d · балл %.1f · %d млн' % (m['inn'], m['nazvanie'][:34], m['region'][:22], FIO[m['ot']],
                                                                    FIO[m['komu']], m['stupen'], m['ball'], m['vyruchka_mln']))
if konflikty:
    print('КОНФЛИКТЫ: %s' % konflikty)
plan = {'vremya': time.strftime('%Y%m%d-%H%M%S'), 'cel': CEL, 'gorod': GOROD, 'dom': DOM,
        'peremeshcheniya': peremeshcheniya, 'ne_doma_do': ne_doma, 'smeshannye_gruppy': smeshannye, 'konflikty': konflikty,
        'krasnodar_inn': sorted(krd), 'altay_inn': sorted(i for i in vse if region[i] == 'Алтайский край'),
        'regiony_do': reg_do, 'regiony_posle': reg_po,
        'milp': {'zapas_stupeney': zs, 'zapas_prochih': zp, 'koridor_balla': kor, 'peremeshcheniy': len(peremeshcheniya), 'minimum': mn},
        'tablica_do': t_do, 'tablica_posle': t_po}
io.open(OUT, 'w', encoding='utf-8').write(json.dumps(plan, ensure_ascii=False, indent=1))
print('план: %s' % OUT)
