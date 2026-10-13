# -*- coding: utf-8 -*-
r"""fixQ_vid (13.10): строка «Покупатель Meyer: …» в шапке карточки – только шаблон (Python не меняется, перезапуск не нужен:
шаблоны панель перечитывает сама).

Вердикт 15 + 12 оценщиков 13.10 лежит в каталоге (fixQ_zamena.py): company.meyer_verdikt («покупатель» / «неясно» /
«не покупатель»), _napravlenie (сортировка / рентген / оба), _uverennost, _pochemu, _dokaz, _data. В карточке:
  «Покупатель Meyer: да – рентген · <почему>» (зелёная строка),
  «Покупатель Meyer: неясно – уточнить звонком: <почему>» (жёлтая; владелец: «неясно – оставить с пометкой»),
  «Покупатель Meyer: нет – <почему>» (красная; в рабочей панели таких нет, на случай оставленных),
  справа «доказательство» (раскрывается: поле/ссылка, уверенность, дата оценки); подсказка при наведении.
Строка – отдельный абзац между шапкой и описанием (на телефоне описание шапки скрыто, строка остаётся).

Что меняется (по уникальным якорям, чтение-правка-запись под замком C:\centro2\_zamok.txt): templates/centro.html.
    python3 zapusk_na_servere.py fixQ_vid.py --suho       # stage-копия кода и копии баз: правка + проверка, живое не трогается
    python3 zapusk_na_servere.py fixQ_vid.py --primenit   # под замком: проверка на stage -> запись -> проверка живого кода
    python3 zapusk_na_servere.py fixQ_vid.py --proverka   # только проверка живого кода (на копиях баз)
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
STAGE = os.path.join(KOREN, '_bekap', 'fixQ-stage')
PRODAVCY = ['meyer%d' % i for i in range(1, 10)]
FAJLY = {'C': 'templates/centro.html'}
SREDA = dict(os.environ, PYTHONIOENCODING='utf-8')

C1_STARO = '''    <div class="hero-opis">{{ opis_kompanii() }}</div>'''
C1_NOVO = ('''    {# fixQ-verdikt 13.10: покупатель Meyer или нет – вердикт оценщиков #}'''
           '''{% set _мвв = (company.get('meyer_verdikt') or '')|string|trim %}{% if _мвв %}'''
           '''{% set _мвн = (company.get('meyer_verdikt_napravlenie') or '')|string|trim %}'''
           '''{% set _мвн = {'оба': 'сортировка и рентген', '-': '', '—': ''}.get(_мвн, _мвн) %}'''
           '''{% set _мвп = (company.get('meyer_verdikt_pochemu') or '')|string|trim %}'''
           '''{% set _мвд = (company.get('meyer_verdikt_dokaz') or '')|string|trim %}'''
           '''{% set _мвu = (company.get('meyer_verdikt_uverennost') or '')|string|trim %}'''
           '''<p class="mv-stroka mv-{{ {'покупатель': 'da', 'не покупатель': 'net'}.get(_мвв, 'nyasno') }}" '''
           '''title="Оценка {{ company.get('meyer_verdikt_data') or '13.10' }}: покупатель ли компания оборудования Meyer '''
           '''(оптическая сортировка сыпучего потока, рентген упакованной продукции).{% if _мвд %} Доказательство: {{ _мвд }}.{% endif %}'''
           '''{% if _мвu %} Уверенность: {{ _мвu }}.{% endif %}">'''
           '''<b class="mv-zag">Покупатель Meyer: {{ {'покупатель': 'да', 'не покупатель': 'нет'}.get(_мвв, _мвв) }}</b>'''
           '''{% if _мвв == 'покупатель' %} – <b>{{ _мвн or 'направление не указано' }}</b>{% if _мвп %}'''
           '''<span class="mv-pochemu"> · {{ _мвп }}</span>{% endif %}'''
           '''{% elif _мвв == 'неясно' %} – уточнить звонком: <span class="mv-pochemu">{{ _мвп or 'профиль производства' }}</span>'''
           '''{% if _мвн %} <span class="mv-napr">(если да – {{ _мвн }})</span>{% endif %}'''
           '''{% else %}{% if _мвп %} – <span class="mv-pochemu">{{ _мвп }}</span>{% endif %}{% endif %}'''
           '''{% if _мвд or _мвu %}<details class="mv-dok"><summary>доказательство</summary><span class="mv-dok-tekst">'''
           '''{{ _мвд or 'не указано' }}{% if _мвu %} · уверенность: {{ _мвu }}{% endif %}'''
           '''{% if company.get('meyer_verdikt_data') %} · оценка {{ company.get('meyer_verdikt_data') }}{% endif %}'''
           '''</span></details>{% endif %}</p>{% endif %}
''' + C1_STARO)
C2_STARO = '''</style>
</body>'''
C2_NOVO = '''</style>
<style id="fixQ-verdikt">
/* fixQ 13.10: строка «Покупатель Meyer: да / неясно / нет» в шапке карточки */
.mv-stroka{margin:8px 0 0;padding:6px 10px;border:1px solid;border-radius:8px;font-size:13px;line-height:1.45;
  max-width:100%;box-sizing:border-box;overflow-wrap:anywhere;cursor:help}
.mv-da{background:#e8f6ee;border-color:#8fd0a8;color:#17462a}
.mv-nyasno{background:#fff6df;border-color:#efc56b;color:#5c3b00}
.mv-net{background:#fdecec;border-color:#efa3a3;color:#7a1c1c}
.mv-zag{font-weight:700}
.mv-pochemu{color:#33373e;font-weight:400}
.mv-napr{color:#5b616b;font-size:12px}
.mv-dok{display:inline-block;margin-left:6px;font-size:12px;cursor:auto}
.mv-dok>summary{cursor:pointer;text-decoration:underline dotted}
.mv-dok-tekst{display:block;margin-top:3px;color:#33373e;font-weight:400}
</style>
</body>'''
PRAVKI = [('C', 'карточка: строка «Покупатель Meyer» в шапке', C1_STARO, C1_NOVO),
          ('C', 'стили fixQ-verdikt', C2_STARO, C2_NOVO)]


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
    from markupsafe import escape as H_escape
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
    kol = {r[1] for r in k.execute('PRAGMA table_info(company)')}
    est_v = 'meyer_verdikt' in kol
    komp = {r['inn']: dict(r) for r in k.execute('SELECT inn, predpriyatie, bazy%s FROM company' % (
        ', meyer_verdikt, meyer_verdikt_napravlenie, meyer_verdikt_pochemu' if est_v else ''))}
    s = sqlite3.connect('file:%s?mode=ro' % sales_db, uri=True)
    nazn = dict(s.execute('SELECT inn, username FROM company_assignment').fetchall())
    skr = {str(r[0]) for r in s.execute("SELECT inn FROM hidden_item WHERE kind='company'")}
    ok(est_v, 'в каталоге есть колонки вердикта (meyer_verdikt…)')
    rx_mv = re.compile(r'<p class="mv-stroka mv-(\w+)"[^>]*><b class="mv-zag">Покупатель Meyer: ([^<]+)</b>(.*?)</p>', re.S)

    def ozhid(c):
        v = (c.get('meyer_verdikt') or '').strip()
        return {'покупатель': ('da', 'да'), 'неясно': ('nyasno', 'неясно'), 'не покупатель': ('net', 'нет')}.get(v) if v else None
    primery = []
    for uslovie in (lambda c: c.get('meyer_verdikt') == 'покупатель' and c.get('meyer_verdikt_napravlenie') == 'рентген',
                    lambda c: c.get('meyer_verdikt') == 'покупатель' and c.get('meyer_verdikt_napravlenie') == 'сортировка',
                    lambda c: c.get('meyer_verdikt') == 'покупатель' and c.get('meyer_verdikt_napravlenie') == 'оба',
                    lambda c: c.get('meyer_verdikt') == 'неясно',
                    lambda c: c.get('meyer_verdikt') == 'неясно' and not c.get('meyer_verdikt_napravlenie'),
                    lambda c: 'замена' in (c.get('bazy') or ''),
                    lambda c: 'замена' in (c.get('bazy') or '') and c['inn'] > '5',
                    lambda c: not c.get('meyer_verdikt')):
        i = next((i for i, c in sorted(komp.items()) if est_v and uslovie(c) and i in nazn and i not in skr and i not in primery), None)
        if i:
            primery.append(i)
    with TestClient(vnutr) as kl:
        kto['u'] = ADMIN
        for nazv, u in (('главная', '/centro'), ('статистика', '/centro/stats'), ('CSV', '/centro/vygruzka.csv')):
            o = kl.get(PUT + u)
            ok(o.status_code == 200, 'админ, %s: %s' % (nazv, o.status_code))
        for n_, p in enumerate(PRODAVCY, 1):
            kto['u'] = {'id': n_, 'username': p, 'role': 'sales', 'is_active': 1}
            o1, o2 = kl.get(PUT + '/centro'), kl.get(PUT + '/centro/stats')
            ok(o1.status_code == 200 and o2.status_code == 403, '%s: главная %s, статистика %s' % (p, o1.status_code, o2.status_code))
        for i in primery:
            vl = nazn[i]
            c = komp[i]
            for kak in (ADMIN, {'id': 1 + PRODAVCY.index(vl), 'username': vl, 'role': 'sales', 'is_active': 1}):
                kto['u'] = kak
                o = kl.get(PUT + '/centro', params={'inn': i})
                hero = o.text.split('<section class="company-hero', 1)[-1].split('</section>', 1)[0]
                m = rx_mv.search(hero)
                oz = ozhid(c)
                tekst = re.sub(r'<[^>]+>', ' ', m.group(3)) if m else ''
                napr = {'оба': 'сортировка и рентген'}.get(c.get('meyer_verdikt_napravlenie') or '', c.get('meyer_verdikt_napravlenie') or '')
                if oz is None:
                    good = o.status_code == 200 and not m
                else:
                    good = (o.status_code == 200 and m is not None and (m.group(1), m.group(2).strip()) == oz
                            and 'class="hero-opis"' in hero and '<h1>' in hero
                            and (oz[0] != 'nyasno' or 'уточнить звонком' in tekst)
                            and (oz[0] != 'da' or (napr and napr in tekst))
                            and str(H_escape((c.get('meyer_verdikt_pochemu') or '')[:40])) in m.group(3))
                ok(good, 'карточка %s (%s; %s / %s): %s; строка %s' % (
                    i, kak['username'], c.get('meyer_verdikt') or 'без вердикта', c.get('meyer_verdikt_napravlenie') or '–',
                    o.status_code, (m.group(1), m.group(2).strip()) if m else 'нет'))
        kto['u'] = ADMIN
        o = kl.get(PUT + '/centro/stats')
        ok(o.status_code == 200, 'админ, статистика после всего: %s' % o.status_code)
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

PAPKA = os.path.join(KOREN, '_bekap', 'fixQ-vid-' + VREMYA)
os.makedirs(PAPKA, exist_ok=True)
if '--proverka' in sys.argv:
    tk, ts = kopii_baz(PAPKA, 'zhivoy')
    g, v = zapustit_proverku(KOREN, tk, ts)
    ubrat(tk, ts)
    io.open(os.path.join(DROP, 'fixQ-vid-proverka-%s.txt' % VREMYA), 'w', encoding='utf-8').write(v)
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
    io.open(os.path.join(DROP, 'fixQ-vid-suho-%s.txt' % VREMYA), 'w', encoding='utf-8').write(t)
    print(t[-5000:])
    print('СУХОЙ ПРОГОН: %s (живые файлы не тронуты; меняются: %s)' % ('ОК' if g else 'ЕСТЬ ПЛОХОЕ', ', '.join(FAJLY[k_] for k_ in izm)))
    raise SystemExit(0)

if '--primenit' in sys.argv:
    vzyat_zamok('fixQ (строка «Покупатель Meyer» в карточке: шаблон)')
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
            io.open(os.path.join(DROP, 'fixQ-vid-primenit-%s.txt' % VREMYA), 'w', encoding='utf-8').write(t)
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
        io.open(os.path.join(DROP, 'fixQ-vid-primenit-%s.txt' % VREMYA), 'w', encoding='utf-8').write(t)
        print(t[-5500:])
    finally:
        otdat_zamok()
