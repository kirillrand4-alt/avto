# -*- coding: utf-8 -*-
r"""fixS_vid (13.10): показ меток Битрикса менеджеру по продажам – только шаблоны (Python не меняется, перезапуск не нужен:
шаблоны панель перечитывает сама).

Что меняется (по уникальным якорям, чтение-правка-запись под замком C:\centro2\_zamok.txt):
  templates/_ochered_spisok.html – в строке очереди под названием заметные метки «Битрикс: КЦ», «Битрикс: СЦ»,
      «Битрикс: Meyer провалено», «Meyer: клиент» («Meyer: успешное привлечение») с подсказкой (число сделок, воронки,
      последняя дата – из company.bitrix_metki_podrobno); у балла – «Битрикс», если ступень 600 дана меткой Битрикса
      (company.stupen_prichina и балл 600–800); подсказка столбца «Балл очереди» – правило 600.
  templates/centro.html – те же метки в шапке карточки + «сделки» (раскрывается: по каждой метке, общая воронка,
      связь); у «Балл очереди» – «ступень 600 – Битрикс: …»; подсказка шкалы ступеней; подсказка отбора «Есть в
      Битриксе» (метки в него входят: все компании с меткой имеют bitrix_kc=1 – это проверяется); стили fixS-bitrix.

    python3 zapusk_na_servere.py fixS_vid.py --suho       # stage-копия кода и копии баз: правки + проверка, живое не трогается
    python3 zapusk_na_servere.py fixS_vid.py --primenit   # под замком: проверка на stage -> запись -> проверка живого кода
    python3 zapusk_na_servere.py fixS_vid.py --proverka   # только проверка живого кода (на копиях баз)
"""
import collections
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
STAGE = os.path.join(KOREN, '_bekap', 'fixS-stage')
PRODAVCY = ['meyer%d' % i for i in range(1, 10)]
FAJLY = {'L': 'templates/_ochered_spisok.html', 'C': 'templates/centro.html'}
SREDA = dict(os.environ, PYTHONIOENCODING='utf-8')


def chip(v):
    """Метки компании (v – 'c' в списке, 'company' в карточке): по одной на метку, подсказка – из «подробно»."""
    return ('{%% if %(v)s.get(\'bitrix_metki\') %%}{%% set _бп = (%(v)s.get(\'bitrix_metki_podrobno\') or \'\')|string %%}'
            '<span class="bx-metki">{%% for _m in (%(v)s.get(\'bitrix_metki\')|string).split(\' · \') %%}{%% set _ч = [] %%}'
            '{%% for _x in _бп.split(\' | \') %%}{%% if _x.startswith(_m ~ \':\') %%}{%% set _ = _ч.append(_x[(_m|length) + 1:]|trim) %%}'
            '{%% endif %%}{%% endfor %%}<span class="bx-metka bx-{{ {\'КЦ\': \'kc\', \'СЦ\': \'sc\', \'Meyer провалено\': \'mp\'}.get(_m, \'mk\') }}" '
            'title="{{ _m }}{%% if _ч %%}: {{ _ч[0] }}{%% endif %%}. Выгрузка Битрикса 09.10; контакты компании – в карточке Битрикса">'
            '{{ {\'Meyer клиент\': \'Meyer: клиент\', \'Meyer привлечение успешно\': \'Meyer: успешное привлечение\'}.get(_m, \'Битрикс: \' ~ _m) }}'
            '</span>{%% endfor %%}' % {'v': v})


L1_STARO = '''<span class="baza-metka">{{ b }}</span>{% endif %}{% endfor %}{% endif %}
          {% if c.get('pometka_ocheredi') %}<br><span class="pometka-och">'''
L1_NOVO = ('''<span class="baza-metka">{{ b }}</span>{% endif %}{% endfor %}{% endif %}'''
           '''{# fixS-bitrix-metki 13.10: «есть в Битриксе: КЦ / СЦ / Meyer провалено», «Meyer: клиент» #}'''
           + chip('c') + '''</span>{% endif %}
          {% if c.get('pometka_ocheredi') %}<br><span class="pometka-och">''')
L2_STARO = '''{% else %}{{ '%.1f'|format(c.assignment_score or 0) }}{% endif %}</td>'''
L2_NOVO = ('''{% else %}{{ '%.1f'|format(c.assignment_score or 0) }}{# fixS-stupen #}{% if c.get('stupen_prichina') and '''
           '''(c.assignment_score or 0) >= 600 and (c.assignment_score or 0) < 800 %}<span class="bx-stupen" title="Ступень 600 – '''
           '''{{ c.get('stupen_prichina') }}: метка Битрикса – не хуже ЛПР с личным мобильным">Битрикс</span>{% endif %}{% endif %}</td>''')
SHKALA_STARO = '600 ЛПР с личным мобильным, 400'
SHKALA_NOVO = '600 ЛПР с личным мобильным или метка Битрикса (КЦ, СЦ, Meyer провалено, Meyer клиент), 400'
C1_STARO = ('''{% set _бх = company.bitrix_kc_info|bitrix_razbor(company.bitrix_kc, company.get('bitrix_klient_sc'), '''
            '''company.get('bitrix_sdelok')) %}{% if company.bitrix_kc or _бх.est %}<span class="bitrix-blok"''')
C1_NOVO = ('''{# fixS-bitrix-metki 13.10 #}''' + chip('company')
           + '''<details class="bx-podr"><summary>сделки</summary><span class="bx-podr-tekst">{% for _x in _бп.split(' | ') %}'''
             '''{{ _x }}{% if not loop.last %}<br>{% endif %}{% endfor %}{% if company.get('bitrix_metki_istochnik') %}<br>'''
             '''<span class="tiho">{{ company.get('bitrix_metki_istochnik') }}</span>{% endif %}</span></details></span>{% endif %}'''
           + C1_STARO)
C2_STARO = '''else '–' }}{% endif %}</span>{% if company.moy_prioritet %}'''
C2_NOVO = ('''else '–' }}{% endif %}{# fixS-stupen #}{% if company.get('stupen_prichina') and company.assignment_score is not none '''
           '''and company.assignment_score|float >= 600 and company.assignment_score|float < 800 %}<span class="bx-stupen">ступень 600 – '''
           '''{{ company.get('stupen_prichina') }}</span>{% endif %}</span>{% if company.moy_prioritet %}''')
C3_STARO = 'title="Есть сделки в Битриксе (КЦ, СЦ или Meyer) по ИНН компании, выгрузка 09.10"'
C3_NOVO = ('title="Есть сделки в Битриксе (КЦ, СЦ, Meyer или общая воронка) по ИНН/УНП компании, выгрузка 09.10. '
           'Сюда входят все компании с метками «Битрикс: КЦ», «Битрикс: СЦ», «Битрикс: Meyer провалено», «Meyer: клиент»"')
C4_STARO = '''</style>
</body>'''
C4_NOVO = '''</style>
<style id="fixS-bitrix">
/* fixS 13.10: метки Битрикса «КЦ / СЦ / Meyer провалено / Meyer клиент» в списке и в шапке карточки; ступень 600 по Битриксу */
.bx-metki{display:inline-flex;flex-wrap:wrap;gap:3px;margin-left:6px;vertical-align:middle}
.och-tab .bx-metki{display:flex;margin:3px 0 1px}
.bx-metka{display:inline-block;padding:1px 7px;border:1px solid;border-radius:999px;font-size:11px;font-weight:700;
  line-height:1.5;white-space:nowrap;cursor:help}
.bx-kc,.bx-sc{background:#eaf1ff;border-color:#9db9f2;color:#1d4ed8}
.bx-mp{background:#fff3e0;border-color:#f3b562;color:#8a4b00}
.bx-mk{background:#e8f6ee;border-color:#8fd0a8;color:#17663a}
.bx-stupen{display:block;margin-top:2px;font-size:11px;font-weight:700;color:#1d4ed8;white-space:nowrap}
.hero-meta .bx-stupen{display:inline;margin-left:6px;white-space:normal}
.bx-podr{display:inline-block;margin-left:2px;font-size:12px}
.bx-podr>summary{cursor:pointer;color:#1d4ed8;text-decoration:underline dotted}
.bx-podr-tekst{display:block;max-width:640px;margin-top:3px;color:#33373e;font-weight:400;white-space:normal}
</style>
</body>'''
PRAVKI = [('L', 'список: метки Битрикса под названием', L1_STARO, L1_NOVO),
          ('L', 'список: «Битрикс» у балла (ступень 600)', L2_STARO, L2_NOVO),
          ('L', 'список: подсказка шкалы ступеней', SHKALA_STARO, SHKALA_NOVO),
          ('C', 'карточка: метки Битрикса и «сделки» в шапке', C1_STARO, C1_NOVO),
          ('C', 'карточка: «ступень 600 – Битрикс» у балла', C2_STARO, C2_NOVO),
          ('C', 'карточка: подсказка шкалы ступеней', SHKALA_STARO, SHKALA_NOVO),
          ('C', 'главная: подсказка отбора «Есть в Битриксе»', C3_STARO, C3_NOVO),
          ('C', 'стили fixS-bitrix', C4_STARO, C4_NOVO)]


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
    komp = {r['inn']: dict(r) for r in k.execute('SELECT inn, predpriyatie, bitrix_kc, bitrix_metki, stupen_prichina FROM company')}
    s = sqlite3.connect('file:%s?mode=ro' % sales_db, uri=True)
    s.row_factory = sqlite3.Row
    nazn = {r['inn']: dict(r) for r in s.execute('SELECT inn, username, assignment_score, stupen_ocheredi FROM company_assignment')}
    skr = {str(r[0]) for r in s.execute("SELECT inn FROM hidden_item WHERE kind='company'")}
    metki = {i for i, c in komp.items() if c['bitrix_metki']}
    podn = {i for i, c in komp.items() if c['stupen_prichina'] and i in nazn and 600 <= (nazn[i]['assignment_score'] or 0) < 800}
    rx_tr = re.compile(r'<tr data-href="[^"]*centro\?inn=(\d+)[^"]*">(.*?)</tr>', re.S)
    rx_bx = re.compile(r'class="bx-metka bx-\w+"[^>]*>([^<]+)</span>')
    rx_fb = re.compile(r'name="bitrix" value="1"[^>]*>\s*Есть в Битриксе · (\d+)')

    def spisok(kl, params, kak):
        kto['u'] = kak
        out, st = [], 1
        while True:
            o = kl.get(PUT + '/centro', params=dict(params, size=100, page=st))
            if o.status_code != 200:
                return None, o.status_code, ''
            r = rx_tr.findall(o.text)
            out += r
            if len(r) < 100 or st > 30:
                return out, 200, o.text if st == 1 else pervaya
            if st == 1:
                pervaya = o.text
            st += 1

    def ozhid_metki(i):
        return [{'Meyer клиент': 'Meyer: клиент', 'Meyer привлечение успешно': 'Meyer: успешное привлечение'}.get(m, 'Битрикс: ' + m)
                for m in (komp[i]['bitrix_metki'] or '').split(' · ') if m]
    with TestClient(vnutr) as kl:
        kto['u'] = ADMIN
        for nazv, u in (('главная', '/centro'), ('статистика', '/centro/stats'), ('CSV', '/centro/vygruzka.csv')):
            o = kl.get(PUT + u)
            ok(o.status_code == 200, 'админ, %s: %s' % (nazv, o.status_code))
        # список директора целиком: метки и «Битрикс» у балла – ровно у кого должны
        stroki, kod, html1 = spisok(kl, {}, ADMIN)
        ok(kod == 200, 'админ, список всех: %s, строк %d' % (kod, len(stroki or [])))
        vidimye = {i for i in nazn if i not in skr}
        ok({i for i, _ in stroki} == vidimye, 'админ: в списке все %d назначенных (без скрытых)' % len(vidimye))
        s_metkoy = {i for i, telo in stroki if 'class="bx-metka' in telo}
        ok(s_metkoy == metki & vidimye, 'список: метки Битрикса у %d строк, ожидалось %d (лишние %s, нет %s)' % (
            len(s_metkoy), len(metki & vidimye), sorted(s_metkoy - metki)[:3], sorted((metki & vidimye) - s_metkoy)[:3]))
        nevern = [i for i, telo in stroki if i in metki and rx_bx.findall(telo) != ozhid_metki(i)]
        ok(not nevern, 'список: текст меток совпадает с bitrix_metki (несовпадений %d %s)' % (len(nevern), nevern[:3]))
        s_stup = {i for i, telo in stroki if 'class="bx-stupen"' in telo}
        ok(s_stup == podn & vidimye, 'список: «Битрикс» у балла – %d строк, ожидалось %d' % (len(s_stup), len(podn & vidimye)))
        # отбор «Есть в Битриксе»: число у галочки = строки; все с меткой – в нём
        for kak in [ADMIN] + [{'id': n, 'username': p, 'role': 'sales', 'is_active': 1} for n, p in enumerate(PRODAVCY, 1)]:
            kto['u'] = kak
            o = kl.get(PUT + '/centro')
            m = rx_fb.search(o.text)
            chislo = int(m.group(1)) if m else -1
            st_, kod, _ = spisok(kl, {'bitrix': '1'}, kak)
            moi = {i for i in vidimye if kak['role'] == 'admin' or nazn[i]['username'] == kak['username']}
            bez = (metki & moi) - {i for i, _ in (st_ or [])}
            ok(o.status_code == 200 and kod == 200 and chislo == len(st_ or []) and not bez,
               '%s: главная %s; «Есть в Битриксе · %d» = строк %d; с меткой не вошли %d' % (
                   kak['username'], o.status_code, chislo, len(st_ or []), len(bez)))
            if kak['role'] == 'sales':
                o = kl.get(PUT + '/centro/stats')
                ok(o.status_code == 403, '%s: статистика менеджеру закрыта: %s' % (kak['username'], o.status_code))
                st_all, kod, _ = spisok(kl, {}, kak)
                mm = {i for i, telo in (st_all or []) if 'class="bx-metka' in telo}
                ok(kod == 200 and mm == metki & moi, '%s: список %s, строк %d, с метками %d (ожидалось %d)' % (
                    kak['username'], kod, len(st_all or []), len(mm), len(metki & moi)))
        # карточки: с метками (разные виды) и без – админ и владелец-менеджер
        primery = []
        for uslovie in (lambda c: 'КЦ' in (c['bitrix_metki'] or '') and 'СЦ' in (c['bitrix_metki'] or ''),
                        lambda c: 'Meyer провалено' in (c['bitrix_metki'] or ''),
                        lambda c: 'Meyer клиент' in (c['bitrix_metki'] or ''),
                        lambda c: 'Meyer привлечение' in (c['bitrix_metki'] or ''),
                        lambda c: bool(c['stupen_prichina']),
                        lambda c: not c['bitrix_metki'] and c['bitrix_kc'],
                        lambda c: not c['bitrix_metki'] and not c['bitrix_kc']):
            i = next((i for i, c in sorted(komp.items()) if uslovie(c) and i in vidimye and i not in primery), None)
            if i:
                primery.append(i)
        for i in primery:
            vl = nazn[i]['username']
            for kak in (ADMIN, {'id': 1 + PRODAVCY.index(vl), 'username': vl, 'role': 'sales', 'is_active': 1}):
                kto['u'] = kak
                o = kl.get(PUT + '/centro', params={'inn': i})
                hero = o.text.split('class="hero-badges"', 1)[-1].split('</div>', 1)[0]
                meta = o.text.split('class="hero-meta"', 1)[-1].split('</div>', 1)[0]
                est = rx_bx.findall(hero)
                ok(o.status_code == 200 and est == ozhid_metki(i) and (('bx-podr' in hero) == bool(komp[i]['bitrix_metki']))
                   and (('class="bx-stupen"' in meta) == (i in podn)),
                   'карточка %s (%s) %s: %s; метки %s; «ступень 600 – Битрикс»: %s' % (
                       i, kak['username'], (komp[i]['bitrix_metki'] or 'без меток'), o.status_code, est, 'class="bx-stupen"' in meta))
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
    vyvod.append('----- stage (новые шаблоны, копии баз)\n' + v)
    ubrat(tk, ts)
    return g


if '--render' in sys.argv:
    i = sys.argv.index('--render')
    raise SystemExit(1 if proverka(*sys.argv[i + 1:i + 4]) else 0)

PAPKA = os.path.join(KOREN, '_bekap', 'fixS-vid-' + VREMYA)
os.makedirs(PAPKA, exist_ok=True)
if '--proverka' in sys.argv:
    tk, ts = kopii_baz(PAPKA, 'zhivoy')
    g, v = zapustit_proverku(KOREN, tk, ts)
    ubrat(tk, ts)
    io.open(os.path.join(DROP, 'fixS-vid-proverka-%s.txt' % VREMYA), 'w', encoding='utf-8').write(v)
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
    io.open(os.path.join(DROP, 'fixS-vid-suho-%s.txt' % VREMYA), 'w', encoding='utf-8').write(t)
    print(t[-5000:])
    print('СУХОЙ ПРОГОН: %s (живые файлы не тронуты; меняются: %s)' % ('ОК' if g else 'ЕСТЬ ПЛОХОЕ', ', '.join(FAJLY[k_] for k_ in izm)))
    raise SystemExit(0)

if '--primenit' in sys.argv:
    vzyat_zamok('fixS (метки Битрикса: шаблоны списка и карточки)')
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
            io.open(os.path.join(DROP, 'fixS-vid-primenit-%s.txt' % VREMYA), 'w', encoding='utf-8').write(t)
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
        io.open(os.path.join(DROP, 'fixS-vid-primenit-%s.txt' % VREMYA), 'w', encoding='utf-8').write(t)
        print(t[-5500:])
    finally:
        otdat_zamok()
