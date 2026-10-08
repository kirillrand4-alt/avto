# -*- coding: utf-8 -*-
"""Одна шапка на все страницы панели Мейера + календарный блок на «Статистике».

Владелец: «когда переходишь между вкладками появляется куча новых шапок. Здесь нужны
будут только “Вся очередь, Взял в работу, Компания не понравилась, Дубль”, а у админа
ещё Статистика; кроме статистики остальное админ видит всю базу; никаких новых шапок».

ПОЧЕМУ ОБЩИЙ ФАЙЛ, А НЕ ПРАВКА КАЖДОЙ ШАПКИ. Шапок было шесть разных (карточка,
статистика, распределение, список, три страницы парка), каждая со своим набором ссылок.
Если поправить каждую, они разъедутся при первой же следующей правке. Поэтому шапка одна
— _shapka.html, — и все страницы её подключают.

СЛЕДСТВИЕ: «Списка компаний» в шапке больше нет, а календарный блок жил на нём. Блок
вынесен в _statblok.html и поставлен на «Статистику» — иначе до него не дойти. На списке
он остаётся тем же файлом, чтобы не было двух копий разметки.

Каждый файл перед правкой копируется в C:\\centro2\\_bekap\\<время>\\.
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
T = os.path.join(APP, 'templates')
PUT = '/obzvon-meyer'
PORT = 8016

VKLADKI = ['Вся очередь', 'Взял в работу', 'Компания не понравилась', 'Дубль — уже работают']

if '--proverka' in sys.argv:
    # =================================================================== ПРОВЕРКА
    import logging
    import warnings
    warnings.filterwarnings('ignore')
    for n in ('httpx', 'httpcore', 'app'):
        logging.getLogger(n).setLevel(logging.CRITICAL)
    os.chdir(KOREN)
    sys.path.insert(0, KOREN)
    try:
        from dotenv import load_dotenv
        load_dotenv(os.path.join(KOREN, '.env'), override=True)
    except Exception:  # noqa: BLE001
        pass
    os.environ['OBZVON_ROOT_PATH'] = PUT
    from app.api import routes_centro_sales as rcs
    from app.obzvon import create_app
    from fastapi.testclient import TestClient

    vnutr = next(z for z in vars(create_app()).values()
                 if hasattr(z, 'routes') and hasattr(z, 'dependency_overrides'))
    plohih = 0

    def proverit(uslovie, tekst):
        global plohih
        if not uslovie:
            plohih += 1
        print('   %s %s' % ('ОК ' if uslovie else 'ПЛОХО', tekst))

    c = sqlite3.connect(os.path.join(KOREN, 'data', 'centro_sales.db'))
    c.execute("attach database ? as centro", (os.path.join(KOREN, 'data', 'centrifugal.db'),))
    inn_parka = c.execute("select a.inn from company_assignment a join centro.company c "
                          "on c.inn=a.inn where a.inn not in (select inn from hidden_item "
                          "where kind='company') limit 1").fetchone()[0]

    def shapka(html):
        m = re.search(r'<header class="topbar">.*?</header>', html, re.S)
        return m.group(0) if m else ''

    def ssylki(sh):
        return [re.sub(r'<[^>]+>', '', x).strip()
                for x in re.findall(r'<a [^>]*>(.*?)</a>', re.search(
                    r'<nav[^>]*>(.*?)</nav>', sh, re.S).group(1), re.S)] if '<nav' in sh else []

    STR = ['/centro', '/centro?call_status=v_rabote', '/centro?call_status=ne_ponravilas',
           '/centro?call_status=dubl', '/centro/stats', '/centro/admin', '/centro/spisok',
           '/centro/park', '/centro/park/%s' % inn_parka]
    for login, rol in (('meyer_admin', 'admin'), ('meyer1', 'sales')):
        print()
        print('########## %s (%s)' % (login, rol))
        vnutr.dependency_overrides[rcs.current_user] = (
            lambda l=login, r=rol: {'id': 0, 'username': l, 'role': r, 'is_active': 1})
        ozhid = VKLADKI + (['Статистика'] if rol == 'admin' else [])
        shapki = {}
        with TestClient(vnutr) as k:
            for s in STR:
                o = k.get(PUT + s, follow_redirects=False)
                if rol == 'sales' and s in ('/centro/stats', '/centro/admin'):
                    proverit(o.status_code == 403, '%-44s -> %s (продавцу закрыто)' % (s, o.status_code))
                    continue
                # 404 с страницей «в парке не показывается» — штатный ответ: компании
                # нет в базе парка. Это страница с шапкой, её тоже проверяем.
                shtatnyy_404 = (o.status_code == 404 and s.startswith('/centro/park/')
                                and 'в парке не показывается' in o.text)
                if o.status_code != 200 and not shtatnyy_404:
                    proverit(False, '%-44s -> %s %s' % (s, o.status_code, o.text[:150]))
                    continue
                sh = shapka(o.text)
                shapki[s] = sh
                proverit(ssylki(sh) == ozhid, '%-44s вкладки %s' % (s, ssylki(sh)))
                adresa = re.findall(r'(?:href|action)="([^"]+)"', sh)
                plohie = [a for a in adresa if not a.startswith(PUT + '/')]
                proverit(not plohie, '%-44s все %d адресов шапки начинаются с %s%s'
                         % (s, len(adresa), PUT, (' — ЧУЖИЕ: %s' % plohie) if plohie else ''))
                if s.startswith('/centro?') or s == '/centro':
                    m = re.search(r'из\s+(\d+)', o.text) or re.search(r'(\d+)\s+компани', o.text)
                    print('      компаний на вкладке: %s' % (m.group(1) if m else '?'))
        # одинаковость: шапки разных страниц совпадают с точностью до отметки активной
        norm = {re.sub(r'\s*class="active"', '', v) for v in shapki.values()}
        proverit(len(norm) == 1, 'шапка одна и та же на всех %d страницах' % len(shapki))
        lishnee = [w for w in ('Список компаний', 'Парк машин', 'Распределение', 'Моя база')
                   if any(w in v for v in shapki.values())]
        proverit(not lishnee, 'в шапках нет лишних ссылок %s' % (lishnee or ''))

    # админ видит всю базу: на вкладках — компании всех продавцов
    print()
    print('########## АДМИН ВИДИТ ВСЮ БАЗУ')
    vnutr.dependency_overrides[rcs.current_user] = lambda: {
        'id': 0, 'username': 'meyer_admin', 'role': 'admin', 'is_active': 1}
    VIDNO = ("s.inn in (select inn from centro.company) and "
             "s.inn not in (select inn from hidden_item where kind='company')")
    with TestClient(vnutr) as k:
        for kod in ('v_rabote', 'ne_ponravilas', 'dubl'):
            ozh = c.execute("select count(*) from company_state s where call_result=? and "
                            + VIDNO, (kod,)).fetchone()[0]
            t = k.get(PUT + '/centro?call_status=' + kod).text
            m = re.search(r'из\s+(\d+)', t) or re.search(r'(\d+)\s+компани', t)
            na_vkladke = int(m.group(1)) if m else -1
            proverit(na_vkladke == ozh, 'вкладка %-14s у админа %s = всех продавцов по базе %s'
                     % (kod, na_vkladke, ozh))

    # календарный блок на статистике
    print()
    print('########## КАЛЕНДАРНЫЙ БЛОК НА «СТАТИСТИКЕ»')
    with TestClient(vnutr) as k:
        t = k.get(PUT + '/centro/stats').text
        t2 = k.get(PUT + '/centro/stats?stat_data=2026-08-11&user=meyer2').text
        sp = k.get(PUT + '/centro/spisok').text
    proverit('<table class="sp-stat-tab">' in t and 'type="date"' in t,
             'на статистике есть календарь и таблица блока')
    for imya in ('Беляев Максим', 'Волков Роман', 'Ерохин Александр', 'Пяткова Ксения'):
        proverit(imya in t.split('<table class="sp-stat-tab">')[1].split('</table>')[0],
                 'в блоке строка «%s»' % imya)
    m = re.search(r'<form class="sp-stat-forma"[^>]*action="([^"]+)"', t)
    proverit(m and m.group(1).endswith('/centro/stats'), 'форма блока ведёт на статистику: %s'
             % (m.group(1) if m else None))
    proverit('name="user" value="meyer2"' in t2,
             'смена даты не сбрасывает открытую очередь продавца')
    proverit('за 11.08.2026' in t2, 'выбранная дата показана в заголовке таблицы')
    proverit('<table class="sp-stat-tab">' in sp, 'на списке блок остался (тем же файлом)')
    print()
    print('ПЛОХИХ ПРОВЕРОК: %d' % plohih)
    raise SystemExit(0)

# ======================================================================= ПРАВКИ
BEKAP = os.path.join(KOREN, '_bekap', time.strftime('odna-shapka-%Y%m%d-%H%M%S'))
nado = sdelano = 0
log = []


def pisat(put, t):
    if os.path.exists(put):
        cel = os.path.join(BEKAP, os.path.relpath(put, KOREN))
        if not os.path.exists(cel):
            os.makedirs(os.path.dirname(cel), exist_ok=True)
            shutil.copy2(put, cel)
    io.open(put, 'w', encoding='utf-8').write(t)


def pravka(put, staro, novo, imya, funkciya=None, priznak=None, regex=False):
    global nado, sdelano
    nado += 1
    t = io.open(put, encoding='utf-8').read()
    i, j = 0, len(t)
    if funkciya:
        i = t.find(funkciya)
        if i < 0:
            log.append('[НЕТ ФУНКЦИИ] ' + imya)
            return
        j = t.find('\n@router.', i + len(funkciya))
        j = len(t) if j < 0 else j
    kusok = t[i:j]
    if priznak and priznak in kusok:
        sdelano += 1
        log.append('[уже] ' + imya)
        return
    if regex:
        nashli = list(re.finditer(staro, kusok, re.S))
        if len(nashli) != 1:
            log.append('[ЯКОРЬ: %d] %s — не правлю' % (len(nashli), imya))
            return
        m = nashli[0]
        kusok = kusok[:m.start()] + novo + kusok[m.end():]
    else:
        n = kusok.count(staro)
        if n != 1:
            log.append('[ЯКОРЬ: %d] %s — не правлю' % (n, imya))
            return
        kusok = kusok.replace(staro, novo, 1)
    pisat(put, t[:i] + kusok + t[j:])
    sdelano += 1
    log.append('[ок] ' + imya)


# ---------------------------------------------------------------- общая шапка
SHAPKA = '''{# ЕДИНСТВЕННАЯ шапка панели. Её подключают все страницы, своих шапок у них нет.
   Владелец: «нужны только Вся очередь, Взял в работу, Компания не понравилась, Дубль,
   а у админа ещё Статистика; никаких новых шапок». Не добавлять сюда ссылок по одной
   странице — шапки снова разъедутся. #}
{# Префикс — только obzvon_bp, его задаёт routes_centro_sales. НЕ base_path: в общем
   окружении Jinja это глобальная переменная ДРУГОГО приложения (пустая), и на страницах,
   передающих префикс как bp, шапка вела на /centro вместо /obzvon-meyer/centro. #}
{% set _bp = obzvon_bp %}
{% set _put = request.url.path.rstrip('/') if request is defined else '' %}
{% set _cs = request.query_params.get('call_status', '') if request is defined else '' %}
<style>.topbar nav a.active{font-weight:700;text-decoration:underline;text-underline-offset:5px}</style>
<header class="topbar">
  <div class="brand-block">
    <strong>Центробежные</strong>
    <span>база продаж по компрессорному оборудованию</span>
  </div>
  <nav>
    <a href="{{ _bp }}/centro"{% if _put.endswith('/centro') and not _cs %} class="active"{% endif %}>Вся очередь</a>
    <a href="{{ _bp }}/centro?call_status=v_rabote"{% if _put.endswith('/centro') and _cs == 'v_rabote' %} class="active"{% endif %}>Взял в работу</a>
    <a href="{{ _bp }}/centro?call_status=ne_ponravilas"{% if _put.endswith('/centro') and _cs == 'ne_ponravilas' %} class="active"{% endif %}>Компания не понравилась</a>
    <a href="{{ _bp }}/centro?call_status=dubl"{% if _put.endswith('/centro') and _cs == 'dubl' %} class="active"{% endif %}>Дубль — уже работают</a>
    {% if user is defined and user and user.role == 'admin' %}<a href="{{ _bp }}/centro/stats"{% if _put.endswith('/centro/stats') %} class="active"{% endif %}>Статистика</a>{% endif %}
  </nav>
  {% if user is defined and user %}
  <div class="user-block">
    <span>{{ user.username|fio }} · {{ 'администратор' if user.role == 'admin' else 'продавец' }}</span>
    <form method="post" action="{{ _bp }}/centro/logout"><button class="link-button">Выйти</button></form>
  </div>
  {% endif %}
</header>
'''
pisat(os.path.join(T, '_shapka.html'), SHAPKA)
log.append('[ок] _shapka.html записан')

# Собственная глобальная переменная префикса для шапки — см. комментарий в _shapka.html
RCS_ = os.path.join(APP, 'api', 'routes_centro_sales.py')
nado += 1
t_ = io.open(RCS_, encoding='utf-8').read()
if 'globals["obzvon_bp"]' in t_:
    sdelano += 1
    log.append('[уже] глобальная obzvon_bp')
else:
    pisat(RCS_, t_.rstrip('\n') + '''


# Префикс панели для общей шапки (_shapka.html). Не base_path: в общем окружении Jinja
# base_path — глобальная переменная другого приложения, она пустая, и на страницах,
# которые передают префикс как bp (список, парк), шапка вела на /centro вместо
# /obzvon-meyer/centro. Своё имя, которое больше никто не задаёт.
templates.env.globals["obzvon_bp"] = BP
''')
    sdelano += 1
    log.append('[ок] глобальная obzvon_bp')

STRANICY = ['centro.html', 'centro_stats.html', 'centro_admin.html', 'spisok.html',
            'park.html', 'park_card.html', 'park_net.html']
for f in STRANICY:
    pravka(os.path.join(T, f), r'<header class="topbar">.*?</header>',
           '{% include "_shapka.html" %}', '%s: своя шапка заменена общей' % f,
           priznak='{% include "_shapka.html" %}', regex=True)

# ---------------------------------------------------------------- блок отдельным файлом
SP = os.path.join(T, 'spisok.html')
t = io.open(SP, encoding='utf-8').read()
m = re.search(r'\n    \{# Блок статистики\..*?\n    </div>\n  </section>', t, re.S)
if m and '_statblok.html' not in t:
    blok = m.group(0)[1:-len('\n    </div>\n  </section>') + len('\n    </div>')]
    blok = (blok.replace('action="{{ bp }}/centro/spisok"', 'action="{{ stat_forma }}"')
                .replace('ssylka(stat_data=', 'stat_ssylka(stat_data='))
    STIL = '''<style>
  .sp-stat{min-width:0;display:grid;gap:8px}
  .sp-stat .tiho{color:var(--muted);font-size:12px}
  .sp-stat-forma{display:flex;gap:12px;align-items:end;flex-wrap:wrap;font-size:12px;color:var(--muted)}
  .sp-stat-forma label{display:grid;gap:3px}
  .sp-stat-forma input,.sp-stat-forma select{padding:5px 8px;border:1px solid var(--line);
    border-radius:8px;background:var(--card);color:var(--navy)}
  .sp-stat-forma a{color:var(--blue)}
  table.sp-stat-tab{border-collapse:collapse;width:100%;font-size:12px}
  table.sp-stat-tab th,table.sp-stat-tab td{padding:4px 8px;border-bottom:1px solid var(--line);
    text-align:right;white-space:nowrap;font-variant-numeric:tabular-nums}
  table.sp-stat-tab th{color:var(--muted);font-weight:600}
  table.sp-stat-tab th:first-child,table.sp-stat-tab td:first-child{text-align:left}
  table.sp-stat-tab th.gr{text-align:center}
  table.sp-stat-tab .razd{border-left:1px solid var(--line)}
  table.sp-stat-tab tr.itog td{font-weight:700}
</style>
'''
    ZAG = ('{# Календарный блок статистики. Стоит на «Статистике» и на «Списке компаний»\n'
           '   одним файлом, чтобы не было двух копий разметки. Нужны в контексте:\n'
           '   statblok, sohranit (скрытые поля), stat_forma (куда форма), stat_ssylka. #}\n')
    pisat(os.path.join(T, '_statblok.html'), ZAG + STIL + blok.strip('\n') + '\n')
    log.append('[ок] _statblok.html записан (%d знаков)' % len(blok))
    pravka(SP, m.group(0), '\n    {% include "_statblok.html" %}\n  </section>',
           'spisok.html: блок подключён файлом', priznak='_statblok.html')
elif '_statblok.html' in t:
    log.append('[уже] блок на списке уже файлом')
else:
    nado += 1
    log.append('[ЯКОРЬ: блок на списке не найден] — блок не вынесен')

pravka(os.path.join(APP, 'api', 'routes_park.py'),
       '"statblok": statblok, "sohranit": sohranit}',
       '"statblok": statblok, "sohranit": sohranit,\n'
       '         "stat_forma": "%s/centro/spisok" % BP, "stat_ssylka": ssylka}',
       'список: контекст для файла блока', funkciya='def centro_spisok(',
       priznak='"stat_forma"')

# ---------------------------------------------------------------- блок на «Статистике»
RCS = os.path.join(APP, 'api', 'routes_centro_sales.py')
pravka(RCS,
       '''    obshchee["poslednee_deystvie"] = str(deystviy[1] or "")[:16].replace("T", " ")''',
       '''    obshchee["poslednee_deystvie"] = str(deystviy[1] or "")[:16].replace("T", " ")

    # Календарный блок: тот же расчёт, что на «Списке компаний» (_statblok в
    # routes_park). Импорт внутри функции: модули ссылаются друг на друга.
    import sqlite3 as _sq_st
    from urllib.parse import urlencode as _urlenc_st
    from app.api import routes_park as _rp
    stat_data_param = (request.query_params.get("stat_data") or "").strip()
    try:
        stat_den = (datetime.date.fromisoformat(stat_data_param)
                    if stat_data_param else None)
    except ValueError:
        stat_den, stat_data_param = None, ""
    stat_user = (request.query_params.get("stat_user") or "").strip()
    sc = _sq_st.connect("file:%s?mode=ro" % _rp.SALES_DB, uri=True)
    sc.row_factory = _sq_st.Row
    try:
        sc.execute("attach database ? as centro", ("file:%s?mode=ro" % _rp.CENTRO_DB,))
        statblok = _rp._statblok(sc, user, stat_den, stat_user)
    finally:
        sc.close()

    def stat_ssylka(**kw):
        d = {k: v for k, v in {"stat_data": stat_data_param, "stat_user": stat_user,
                               "user": vybrannyy, **kw}.items() if v}
        return "%s/centro/stats%s" % (BP, ("?" + _urlenc_st(d)) if d else "")''',
       'статистика: расчёт календарного блока', funkciya='def stats_page(',
       priznak='_rp._statblok(')
pravka(RCS, '''            "poisk_param": _STATS_POISK,''',
       '''            "poisk_param": _STATS_POISK,
            "statblok": statblok,
            "sohranit": {"user": vybrannyy} if vybrannyy else {},
            "stat_forma": "%s/centro/stats" % BP,
            "stat_ssylka": stat_ssylka,''',
       'статистика: блок в контекст', funkciya='def stats_page(', priznak='"stat_forma"')

ST = os.path.join(T, 'centro_stats.html')
pravka(ST, '  <h2>Общая статистика</h2>',
       '  <h2>По продавцам: за день и за всё время</h2>\n'
       '  {% include "_statblok.html" %}\n\n'
       '  <h2>Общая статистика</h2>',
       'статистика: календарный блок сверху', priznak='_statblok.html')
pravka(ST, 'href="{{ base_path }}/centro/stats?user={{ p.username }}"',
       'href="{{ stat_ssylka(user=p.username) }}"',
       'статистика: имя продавца открывает очередь, не сбрасывая дату',
       priznak='stat_ssylka(user=p.username)')
pravka(ST, '<main class="admin-page">', '<main class="admin-page" style="padding:16px 22px">',
       'статистика: отступ от края', priznak='style="padding:16px 22px"')

print('правок внесено: %d из %d' % (sdelano, nado))
for s in log:
    print('   ' + s)
print('бэкап: %s' % BEKAP)

# ---------------------------------------------------------------- перезапуск и проверка
r = subprocess.run(['netstat', '-ano'], capture_output=True, timeout=90)
for l in r.stdout.decode('cp866', 'replace').splitlines():
    if (':%d ' % PORT) in l and 'LISTENING' in l.upper():
        subprocess.run(['taskkill', '/PID', l.split()[-1], '/F'], capture_output=True, timeout=60)
time.sleep(2)
lg = io.open(os.path.join(KOREN, 'centro2.log'), 'a', encoding='utf-8', errors='replace')
lg.write('\n===== перезапуск: одна шапка %s =====\n' % time.strftime('%Y-%m-%d %H:%M:%S'))
lg.flush()
subprocess.Popen(
    [VENV, '-m', 'uvicorn', 'app.obzvon:app', '--host', '127.0.0.1', '--port', str(PORT)],
    cwd=KOREN, stdout=lg, stderr=subprocess.STDOUT,
    creationflags=0x00000008 | 0x00000200, close_fds=True,
    env=dict(os.environ, PYTHONIOENCODING='utf-8', OBZVON_ROOT_PATH=PUT,
             ENV_FILE=os.path.join(KOREN, '.env')))
time.sleep(8)
r = subprocess.run([VENV, os.path.abspath(__file__), '--proverka'], capture_output=True,
                   timeout=1500, env=dict(os.environ, PYTHONIOENCODING='utf-8',
                                          OBZVON_ROOT_PATH=PUT))
print()
print('===== ПРОВЕРКА =====')
sys.stdout.write(r.stdout.decode('utf-8', 'replace'))
if r.returncode:
    sys.stdout.write('\n--- stderr ---\n' + r.stderr.decode('utf-8', 'replace')[-2500:])
