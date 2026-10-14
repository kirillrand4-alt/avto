# -*- coding: utf-8 -*-
r"""fixU_opis (14.10): в списке очереди под названием компании, если описания нет, – паспорт компании.

Владелец 14.10 (про «Паспорт компании» – продукция, сырьё, оборудование, упаковка, масштаб): «вот это туда выводи, если
не заполнено сейчас». Список очереди (templates/_ochered_spisok.html) показывает под названием company.opisanie; у 621 из
1 680 компаний (почти все – База 7: в сборке MEYER-7 текст описания был лишь у 1 219 из 16 938) оно пустое. Теперь при
пустом описании там строка «по паспорту: Продукция …; Сырьё …; Оборудование …; Упаковка …; Масштаб …» (каждое поле
обрезано до 160 знаков, полностью – в карточке), а если нет ни продукции, ни паспорта – «справка: <вердикт оценщика
13.10>». Данные не меняются; в карточке паспорт и так стоит на месте описания – она не меняется.

Только шаблон (Python не меняется, перезапуск не нужен), по уникальному якорю, под замком C:\centro2\_zamok.txt.
    python3 zapusk_na_servere.py fixU_opis.py --suho       # stage-копия кода и копии баз: правка + проверка
    python3 zapusk_na_servere.py fixU_opis.py --primenit   # под замком: stage -> запись -> проверка живого кода
    python3 zapusk_na_servere.py fixU_opis.py --proverka   # только проверка живого кода (на копиях баз)
"""
import io
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import time

VENV = r'C:\seostat\.venv\Scripts\python.exe'
KOREN = r'C:\centro2'
APP = os.path.join(KOREN, 'app')
KAT = os.path.join(KOREN, 'data', 'meyer_baza1.db')
SALES = os.path.join(KOREN, 'data', 'centro_sales_meyer1.db')
DROP = r'C:\seostat\drop\drop-storage'
PUT = '/obzvon-meyer'
ZAMOK = r'C:\centro2\_zamok.txt'
VREMYA = time.strftime('%Y%m%d-%H%M%S')
STAGE = os.path.join(KOREN, '_bekap', 'fixU-stage')
PRODAVCY = ['meyer%d' % i for i in range(1, 10)]
FAJLY = {'S': 'templates/_ochered_spisok.html'}
SREDA = dict(os.environ, PYTHONIOENCODING='utf-8')

S1_STARO = """{% if c.opisanie %}<div class="komp-opis">{{ c.opisanie }}</div>{% endif %}"""
S1_NOVO = ("""{% if c.opisanie %}<div class="komp-opis">{{ c.opisanie }}</div>{% else %}"""
           """{# fixU-opis 14.10: описания нет – паспорт компании, иначе справка оценщика #}{% set _пп = [] %}"""
           """{% for _н, _к in [('Продукция', 'produkciya'), ('Сырьё', 'pasport_syrye'), ('Оборудование', 'pasport_oborudovanie'), """
           """('Упаковка', 'pasport_upakovka'), ('Масштаб', 'pasport_masshtab')] %}{% set _з = (c.get(_к) or '')|string|trim %}"""
           """{% if _з %}{% set _ = _пп.append(_н ~ ': ' ~ (_з|truncate(160, True, '…', 0))) %}{% endif %}{% endfor %}"""
           """{% if _пп %}<div class="komp-opis komp-opis-pasp" title="Описания нет – показан паспорт компании (сборка MEYER-7); полностью – в карточке">"""
           """<span class="komp-opis-metka" style="color:#6b7280;font-size:11px;margin-right:4px">по паспорту:</span>{{ _пп|join('; ') }}</div>"""
           """{% elif c.get('meyer_verdikt_pochemu') %}<div class="komp-opis komp-opis-pasp" title="Описания и паспорта нет – справка оценщика 13.10">"""
           """<span class="komp-opis-metka" style="color:#6b7280;font-size:11px;margin-right:4px">справка:</span>{{ c.get('meyer_verdikt_pochemu') }}</div>"""
           """{% endif %}{% endif %}""")
PRAVKI = [('S', 'список очереди: паспорт на месте пустого описания', S1_STARO, S1_NOVO)]


def nl_kak_v(t, x):
    return x.replace('\n', '\r\n') if t.count('\r\n') * 2 > t.count('\n') else x


def nalozhit(teksty):
    novye = dict(teksty)
    zh, ok = [], True
    for kl, imya, staro, novo in PRAVKI:
        t = novye[kl]
        st, nv = nl_kak_v(t, staro), nl_kak_v(t, novo)
        if t.count(nv) == 1:
            zh.append('[уже] ' + imya)
            continue
        n = t.count(st)
        if n != 1:
            zh.append('[ЯКОРЬ НАЙДЕН %d РАЗ] %s' % (n, imya))
            ok = False
            continue
        novye[kl] = t.replace(st, nv, 1)
        zh.append('[ок] ' + imya)
    return novye, zh, ok


def prochitat(koren_app):
    return {k: io.open(os.path.join(koren_app, *p.split('/')), encoding='utf-8', newline='').read() for k, p in FAJLY.items()}


def zapisat(koren_app, teksty, klyuchi):
    for k in klyuchi:
        with io.open(os.path.join(koren_app, *FAJLY[k].split('/')), 'w', encoding='utf-8', newline='') as f:
            f.write(teksty[k])


def kopiya(src, dst):
    a = sqlite3.connect('file:%s?mode=ro' % src, uri=True)
    b = sqlite3.connect(dst)
    a.backup(b)
    b.close()
    a.close()


# ====================================================================== проверка (venv, копии баз)
def proverka(koren, kat, sales_db):
    sys.path.insert(0, KOREN)
    import zapusk  # noqa: F401  – .env в окружение
    sys.path.insert(0, koren)
    import logging
    import warnings
    warnings.filterwarnings('ignore')
    logging.disable(logging.CRITICAL)
    for k in ('CENTRO_SALES_DB', 'PARK_OCHERED_SALES_DB'):
        os.environ[k] = sales_db
    for k in ('CENTRIFUGAL_DB', 'CENTRO_DB', 'PARK_OCHERED_DB'):
        os.environ[k] = kat
    from app import web
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
    ok(os.path.normcase(os.path.dirname(web.__file__)).startswith(os.path.normcase(koren)), 'код: %s' % os.path.dirname(web.__file__))
    ok(str(catalog.db_path()) == kat and str(sales.sales_db_path()) == sales_db, 'базы – временные копии')
    vnutr = next(z for z in vars(create_app()).values() if hasattr(z, 'routes') and hasattr(z, 'dependency_overrides'))
    ADMIN = {'id': 0, 'username': 'meyer_admin', 'role': 'admin', 'is_active': 1}
    kto = {'u': ADMIN}
    vnutr.dependency_overrides[rcs.current_user] = lambda: kto['u']
    k = sqlite3.connect('file:%s?mode=ro' % kat, uri=True)
    k.row_factory = sqlite3.Row
    pusto = lambda c: "COALESCE(TRIM(%s),'')=''" % c  # noqa: E731
    PASP = ('pasport_syrye', 'pasport_oborudovanie', 'pasport_upakovka', 'pasport_masshtab')
    s = sqlite3.connect('file:%s?mode=ro' % sales_db, uri=True)
    nazn = dict(s.execute('SELECT inn, username FROM company_assignment').fetchall())
    vidy = {
        'opis': 'NOT ' + pusto('opisanie'),
        'prod': pusto('opisanie') + ' AND NOT ' + pusto('produkciya'),
        'pasp': pusto('opisanie') + ' AND ' + pusto('produkciya') + ' AND NOT (' + ' AND '.join(pusto(c) for c in PASP) + ')',
        'sprav': pusto('opisanie') + ' AND ' + pusto('produkciya') + ' AND ' + ' AND '.join(pusto(c) for c in PASP)
                 + ' AND NOT ' + pusto('meyer_verdikt_pochemu')}
    vid_inn = {}
    for v, w in vidy.items():
        for r in k.execute('SELECT inn FROM company WHERE ' + w):
            vid_inn[r[0]] = v
    print('   компаний: с описанием %d, по продукции %d, по паспорту %d, справка %d' % tuple(
        sum(1 for x in vid_inn.values() if x == v) for v in ('opis', 'prod', 'pasp', 'sprav')))
    proveren = {'opis': 0, 'prod': 0, 'pasp': 0, 'sprav': 0}
    with TestClient(vnutr) as kl:
        kto['u'] = ADMIN
        for nazv, u in (('главная', '/centro'), ('статистика', '/centro/stats'), ('CSV', '/centro/vygruzka.csv')):
            o = kl.get(PUT + u)
            ok(o.status_code == 200, 'админ, %s: %s' % (nazv, o.status_code))
        for n_, p in enumerate(PRODAVCY, 1):
            kto['u'] = {'id': n_, 'username': p, 'role': 'sales', 'is_active': 1}
            o = kl.get(PUT + '/centro')
            ok(o.status_code == 200, '%s: главная %s' % (p, o.status_code))
            stroki = o.text.split('<tr')
            n_pasp = n_sprav = 0
            for st in stroki:
                m = re.search(r'inn=(\d{9,12})', st)
                if not m or m.group(1) not in vid_inn:
                    continue
                v = vid_inn[m.group(1)]
                est_p = 'komp-opis-pasp' in st
                if v == 'opis':
                    good = 'class="komp-opis"' in st and not est_p
                elif v in ('prod', 'pasp'):
                    good = est_p and 'по паспорту' in st
                else:
                    good = est_p and 'справка' in st
                n_pasp += v in ('prod', 'pasp')
                n_sprav += v == 'sprav'
                if proveren[v] < 400:
                    proveren[v] += 1
                    if not good:
                        ok(False, '%s: строка %s (%s) без ожидаемого описания' % (p, m.group(1), v))
            print('   %s: строк по паспорту %d, со справкой %d, «по паспорту» в разметке %d' % (
                p, n_pasp, n_sprav, o.text.count('komp-opis-pasp')))
        ok(proveren['prod'] + proveren['pasp'] > 0 and proveren['opis'] > 0,
           'проверено строк: с описанием %d, по паспорту %d (продукция) + %d (паспорт), справка %d' % (
               proveren['opis'], proveren['prod'], proveren['pasp'], proveren['sprav']))
        kto['u'] = ADMIN
        i = next((x for x, v in sorted(vid_inn.items()) if v == 'prod' and x in nazn), None)
        if i:
            o = kl.get(PUT + '/centro', params={'inn': i})
            ok(o.status_code == 200 and 'contact-card' in o.text, 'карточка %s: %s' % (i, o.status_code))
    print('ПЛОХИХ ПРОВЕРОК: %d' % plohih[0])
    return plohih[0]


def zapustit_proverku(koren, kat, sales_db):
    r = subprocess.run([VENV, os.path.abspath(__file__), '--render', koren, kat, sales_db], capture_output=True,
                       timeout=1500, cwd=KOREN, env=SREDA)
    v = r.stdout.decode('utf-8', 'replace')
    if r.returncode:
        v += '\n--- stderr ---\n' + r.stderr.decode('utf-8', 'replace')[-3000:]
    return 'ПЛОХИХ ПРОВЕРОК: 0' in v, v


def kopii_baz(papka, metka):
    ts, tk = os.path.join(papka, 't_sales_%s.db' % metka), os.path.join(papka, 't_kat_%s.db' % metka)
    kopiya(SALES, ts)
    kopiya(KAT, tk)
    return tk, ts


def ubrat(*f):
    for x in f:
        try:
            os.remove(x)
        except OSError:
            pass


def vzyat_zamok(kto):
    if os.path.exists(ZAMOK) and time.time() - os.path.getmtime(ZAMOK) > 1500:
        os.remove(ZAMOK)
    try:
        fd = os.open(ZAMOK, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        print('ЗАМОК ЗАНЯТ: ' + io.open(ZAMOK, encoding='utf-8').read())
        raise SystemExit(3)
    os.write(fd, ('%s %s' % (kto, time.strftime('%H:%M:%S'))).encode('utf-8'))
    os.close(fd)


def otdat_zamok():
    try:
        os.remove(ZAMOK)
    except OSError:
        pass


def na_stage(novye, izm, papka, vyvod):
    if os.path.isdir(STAGE):
        shutil.rmtree(STAGE, ignore_errors=True)
    shutil.copytree(APP, os.path.join(STAGE, 'app'), ignore=shutil.ignore_patterns('__pycache__', 'dokaz', '*.pyc', '*.db', '*.log'))
    zapisat(os.path.join(STAGE, 'app'), novye, izm)
    tk, ts = kopii_baz(papka, 'stage')
    g, v = zapustit_proverku(STAGE, tk, ts)
    vyvod.append('----- stage (новый шаблон, копии баз)\n' + v)
    ubrat(tk, ts)
    return g


if '--render' in sys.argv:
    i = sys.argv.index('--render')
    raise SystemExit(1 if proverka(*sys.argv[i + 1:i + 4]) else 0)

PAPKA = os.path.join(KOREN, '_bekap', 'fixU-opis-' + VREMYA)
os.makedirs(PAPKA, exist_ok=True)
if '--proverka' in sys.argv:
    tk, ts = kopii_baz(PAPKA, 'zhivoy')
    g, v = zapustit_proverku(KOREN, tk, ts)
    ubrat(tk, ts)
    io.open(os.path.join(DROP, 'fixU-opis-proverka-%s.txt' % VREMYA), 'w', encoding='utf-8').write(v)
    print(v[-5500:])
    raise SystemExit(0 if g else 5)

if '--suho' in sys.argv:
    teksty = prochitat(APP)
    novye, zh, vse_ok = nalozhit(teksty)
    print('\n'.join('   ' + x for x in zh))
    if not vse_ok:
        raise SystemExit('ЯКОРЯ НЕ НАЙДЕНЫ – ничего не делаю')
    izm = [k_ for k_ in novye if novye[k_] != teksty[k_]]
    vyvod = []
    g = na_stage(novye, izm, PAPKA, vyvod)
    t = '\n'.join(vyvod)
    io.open(os.path.join(DROP, 'fixU-opis-suho-%s.txt' % VREMYA), 'w', encoding='utf-8').write(t)
    print(t[-5000:])
    print('СУХОЙ ПРОГОН: %s (живые файлы не тронуты; меняются: %s)' % ('ОК' if g else 'ЕСТЬ ПЛОХОЕ', ', '.join(FAJLY[k_] for k_ in izm)))
    raise SystemExit(0)

if '--primenit' in sys.argv:
    vzyat_zamok('fixU (описание по паспорту в списке очереди: шаблон)')
    vyvod = []
    try:
        teksty = prochitat(APP)
        novye, zh, vse_ok = nalozhit(teksty)
        print('\n'.join('   ' + x for x in zh))
        if not vse_ok:
            print('ЯКОРЯ НЕ НАЙДЕНЫ – живые файлы не тронуты')
            raise SystemExit(4)
        izm = [k_ for k_ in novye if novye[k_] != teksty[k_]]
        if not izm:
            print('правки уже стоят – файлы не меняю')
            raise SystemExit(0)
        for k_ in izm:                                  # копия прежних файлов – только свои
            dst = os.path.join(PAPKA, 'app', *FAJLY[k_].split('/'))
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy2(os.path.join(APP, *FAJLY[k_].split('/')), dst)
        if not na_stage(novye, izm, PAPKA, vyvod):
            t = '\n'.join(vyvod)
            io.open(os.path.join(DROP, 'fixU-opis-primenit-%s.txt' % VREMYA), 'w', encoding='utf-8').write(t)
            print(t[-4500:])
            print('ПРОВЕРКА НА STAGE НЕ ПРОШЛА – живые файлы не тронуты')
            raise SystemExit(5)
        for k_ in izm:
            if io.open(os.path.join(APP, *FAJLY[k_].split('/')), encoding='utf-8', newline='').read() != teksty[k_]:
                print('ФАЙЛ %s ИЗМЕНИЛСЯ ЗА ВРЕМЯ ПРОГОНА – не пишу' % FAJLY[k_])
                raise SystemExit(6)
        zapisat(APP, novye, izm)
        tk, ts = kopii_baz(PAPKA, 'zhivoy')
        g2, v2 = zapustit_proverku(KOREN, tk, ts)
        ubrat(tk, ts)
        vyvod.append('----- живой код после записи (Python не менялся, перезапуск не нужен)\n' + v2[-4000:])
        if not g2:
            for k_ in izm:
                if io.open(os.path.join(APP, *FAJLY[k_].split('/')), encoding='utf-8', newline='').read() == novye[k_]:
                    shutil.copy2(os.path.join(PAPKA, 'app', *FAJLY[k_].split('/')), os.path.join(APP, *FAJLY[k_].split('/')))
            vyvod.append('ПОСЛЕ ЗАПИСИ ПЛОХО – свои файлы возвращены из %s' % PAPKA)
        else:
            vyvod.append('ПРИМЕНЕНО: %s; копия прежних файлов: %s' % (', '.join(FAJLY[k_] for k_ in izm), PAPKA))
        t = '\n'.join(vyvod)
        io.open(os.path.join(DROP, 'fixU-opis-primenit-%s.txt' % VREMYA), 'w', encoding='utf-8').write(t)
        print(t[-5500:])
    finally:
        otdat_zamok()
