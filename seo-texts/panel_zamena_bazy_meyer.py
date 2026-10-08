# -*- coding: utf-8 -*-
"""Замена базы панели Мейера: «База 1 — ЛПР с мобильными и добавочными», 65 компаний.

Владелец: «замени базу, равномерно распределив по приоритетам на 4-х менеджеров»,
«куда-нибудь отметку воткни База 1 (под вопросиком расшифровка: ЛПР с мобильными и
добавочными)», «название центробежной тоже замени».

ЧТО ДЕЛАЕТСЯ
  1. Каталог C:\\centro2\\data\\meyer_baza1.db — В СХЕМЕ centrifugal.db (код панели не
     меняется), плюс свои колонки: opisanie, popadanie, segment_osn, lpr_kratko.
  2. Продажи C:\\centro2\\data\\centro_sales_meyer1.db — схема текущей базы продаж копии,
     из пользователей — только действующие (meyer_admin, meyer1..meyer4). Чистый лист:
     ни назначений, ни статусов, ни журнала от центробежной базы.
  3. Раздача «змейкой» по баллу панели (company_score): 1-2-3-4-4-3-2-1… У каждого 16–17
     компаний и равная доля сильных. Встроенный assign_new панели раскладывает со
     случайностью внутри групп балла — для «поровну по приоритетам» нужна раскладка,
     которую можно проверить глазами.
  4. .env переключается на новые файлы. СТАРЫЕ centrifugal.db и centro_sales.db НЕ
     ТРОГАЮТСЯ: вернуть — поменять строки в .env обратно (бэкап .env рядом).
  5. Название панели, метка базы — из .env (PANEL_NAZVANIE, PANEL_PODPIS, BAZA_NAZVANIE,
     BAZA_OPISANIE): следующую базу можно подписать, не трогая шаблоны.
  6. Список: «Сегмент» и «ЛПР» вместо компрессорных «Машины / Приговор / Контакты».
     Фильтры «Модель», «Состояние», «Приговор», «Под замену» прячутся, когда у базы для
     них нет ни одного значения — у центробежной базы они бы остались.
"""
import io
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import time

VENV = r'C:\seostat\.venv\Scripts\python.exe'
KOREN = r'C:\centro2'
DATA = os.path.join(KOREN, 'data')
APP = os.path.join(KOREN, 'app')
T = os.path.join(APP, 'templates')
ENV = os.path.join(KOREN, '.env')
PORT = 8016
PUT = '/obzvon-meyer'
JSON_PUT = r'C:\seostat\drop\drop-storage\meyer-baza1.json'
KAT_NEW = os.path.join(DATA, 'meyer_baza1.db')
SALES_NEW = os.path.join(DATA, 'centro_sales_meyer1.db')
KAT_OLD = os.path.join(DATA, 'centrifugal.db')
SALES_OLD = os.path.join(DATA, 'centro_sales.db')
PRODAVCY = ['meyer1', 'meyer2', 'meyer3', 'meyer4']
BEKAP = os.path.join(KOREN, '_bekap', time.strftime('zamena-bazy-%Y%m%d-%H%M%S'))

# ============================================================== ПРОВЕРКА (под venv)
if '--proverka' in sys.argv:
    sys.path.insert(0, KOREN)
    import zapusk  # noqa: F401 — НОВЫЙ .env
    import logging
    import warnings
    warnings.filterwarnings('ignore')
    logging.disable(logging.CRITICAL)
    from app.api import routes_centro_sales as rcs
    from app.obzvon import create_app
    from fastapi.testclient import TestClient

    vnutr = next(z for z in vars(create_app()).values()
                 if hasattr(z, 'routes') and hasattr(z, 'dependency_overrides'))
    d = json.load(io.open(JSON_PUT, encoding='utf-8'))
    plohih = 0

    def proverit(u, t):
        global plohih
        if not u:
            plohih += 1
        print('   %s %s' % ('ОК ' if u else 'ПЛОХО', t))

    def kak(l, r):
        vnutr.dependency_overrides[rcs.current_user] = (
            lambda: {'id': 0, 'username': l, 'role': r, 'is_active': 1})

    print('########## ПУТИ БАЗ У ПРИЛОЖЕНИЯ')
    print('   CENTRIFUGAL_DB=%s' % os.environ.get('CENTRIFUGAL_DB'))
    print('   CENTRO_SALES_DB=%s' % os.environ.get('CENTRO_SALES_DB'))
    kak('meyer_admin', 'admin')
    with TestClient(vnutr) as k:
        o = k.get(PUT + '/centro?size=100')
        m = re.search(r'Компании (\d+)–(\d+) из (\d+)', o.text)
        proverit(o.status_code == 200 and m and int(m.group(3)) == len(d['kompanii']),
                 'список у админа: %s (в файле %d)' % (m.group(0) if m else o.status_code, len(d['kompanii'])))
        sh = re.search(r'<header class="topbar">.*?</header>', o.text, re.S).group(0)
        proverit('Meyer' in sh and 'Центробеж' not in sh, 'в шапке «Meyer», «Центробежных» нет')
        m = re.search(r'title="([^"]*)"[^>]*>\?', sh)
        proverit('База 1' in sh and m and 'мобильными и добавочными' in m.group(1),
                 'метка «База 1», под «?» подсказка: %r' % (m.group(1) if m else None))
        t = re.search(r'<title>(.*?)</title>', o.text).group(1)
        proverit('Центробеж' not in t, 'заголовок вкладки: %r' % t)
        proverit('<th>Сегмент</th>' in o.text and '<th>ЛПР</th>' in o.text and '<th>Машины</th>' not in o.text,
                 'в списке колонки «Сегмент» и «ЛПР»')
        proverit('name="sostoyanie"' not in o.text.split('<dialog')[0] and 'name="verdikt"' not in o.text.split('<dialog')[0],
                 'пустые компрессорные фильтры спрятаны')
        # карточки трёх компаний
        for c in d['kompanii'][:3] + sorted(d['kompanii'], key=lambda x: -x['n_phones'])[:1]:
            o = k.get(PUT + '/centro?inn=' + c['inn'])
            n_k = len([x for x in d['kontakty'] if x['inn'] == c['inn']])
            pokaz = len(re.findall(r'class="contact-card', o.text))
            # кавычки в описании экранируются в HTML — сверяю начало до первого спецсимвола
            frag = re.split(r'["\'&<>«»]', c['opisanie'] or '')[0][:30]
            opis_ok = (not c['opisanie']) or len(frag) < 8 or frag in o.text
            proverit(o.status_code == 200 and pokaz == n_k and opis_ok,
                     'карточка %s: %s, контактов %d из %d, описание %s'
                     % (c['inn'], o.status_code, pokaz, n_k, 'есть' if opis_ok else 'НЕТ'))
        for s in ('/centro/stats', '/centro/spisok', '/centro/admin', '/centro?call_status=v_rabote'):
            o = k.get(PUT + s)
            proverit(o.status_code == 200, '%-30s -> %s' % (s, o.status_code))
        st = k.get(PUT + '/centro/stats').text
        proverit(all(i in st for i in ('Пяткова Ксения', 'Ерохин Александр', 'Беляев Максим', 'Волков Роман')),
                 'статистика видит четверых')
    print()
    print('########## У КАЖДОГО ПРОДАВЦА СВОЯ ОЧЕРЕДЬ')
    for l in PRODAVCY:
        kak(l, 'sales')
        with TestClient(vnutr) as k:
            o = k.get(PUT + '/centro?size=100')
        m = re.search(r'из (\d+)', o.text)
        print('   %s: %s компаний в очереди' % (l, m.group(1) if m else '?'))
    print()
    print('ПЛОХИХ ПРОВЕРОК: %d' % plohih)
    raise SystemExit(0)

# ============================================================== ПОСТРОЕНИЕ (под venv)
if '--postroit' in sys.argv:
    sys.path.insert(0, KOREN)
    import zapusk  # noqa: F401 — пока старый .env; пути передаю явно
    import logging
    logging.disable(logging.CRITICAL)
    from app.services import centro_sales as sales

    d = json.load(io.open(JSON_PUT, encoding='utf-8'))
    for p in (KAT_NEW, SALES_NEW):
        if os.path.exists(p):
            os.makedirs(BEKAP, exist_ok=True)
            shutil.move(p, os.path.join(BEKAP, os.path.basename(p)))
            print('прежний %s убран в бэкап' % os.path.basename(p))

    # ---------- 1. каталог в схеме centrifugal.db
    star = sqlite3.connect('file:%s?mode=ro' % KAT_OLD, uri=True)
    shema = [r for r in star.execute(
        "select type, name, sql from sqlite_master where sql is not null and name<>'sqlite_stat1' "
        "order by case type when 'table' then 0 when 'index' then 1 else 2 end")]
    star.close()
    k = sqlite3.connect(KAT_NEW)
    for tip, imya, sql in shema:
        k.execute(sql)
    for kol in ('opisanie', 'popadanie', 'segment_osn', 'lpr_kratko'):
        k.execute('ALTER TABLE company ADD COLUMN %s TEXT' % kol)
    kol_company = [r[1] for r in k.execute('PRAGMA table_info(company)')]
    for c in d['kompanii']:
        kont = [x for x in d['kontakty'] if x['inn'] == c['inn']]
        z = dict(c)
        z['has_purchaser'] = int(c['n_purchaser'] > 0)
        z['has_tech'] = int(c['n_tech'] > 0)
        z['n_signals'] = 0
        z['n_facts'] = 0
        z['search_blob'] = ' '.join(str(x) for x in (
            c['inn'], c['predpriyatie'], c['region'], c['okvedy_vse'], c['segment'], c['opisanie'],
            c['sayt'], c['lpr_kratko'], ' '.join((x['person'] or '') + ' ' + x['position'] + ' ' + x['cifry'] for x in kont)
        ) if x).lower()
        z = {kk: v for kk, v in z.items() if kk in kol_company}
        k.execute('INSERT INTO company (%s) VALUES (%s)' % (
            ','.join('"%s"' % kk for kk in z), ','.join('?' * len(z))), list(z.values()))
    for x in d['kontakty']:
        k.execute('INSERT INTO contact (inn, value, kind, person, role, position, phone_type, source, '
                  'source_url, is_purchaser, is_tech, has_role, is_unknown_owner) '
                  'VALUES (?,?,?,?,?,?,?,?,?,?,?,?,0)',
                  (x['inn'], x['value'], 'phone', x['person'], x['role'], x['position'], x['phone_type'],
                   x['source'], x['source_url'], x['is_purchaser'], x['is_tech'], x['has_role']))
        if x['person']:
            k.execute('INSERT INTO person (inn, person, position, role, phone, phone_type, source_url, '
                      'source, is_tech) VALUES (?,?,?,?,?,?,?,?,?)',
                      (x['inn'], x['person'], x['position'], x['role'], x['value'], x['phone_type'],
                       x['source_url'], x['source'], x['is_tech']))
        if x['source_url']:
            k.execute('INSERT INTO company_source (inn, field_name, source, source_url) VALUES (?,?,?,?)',
                      (x['inn'], 'ЛПР: %s' % x['position'], x['source'].split(' · ')[0], x['source_url']))
    for kk, v in {
        'source_kind': 'meyer-xlsx', 'baza': 'База 1 — ЛПР с мобильными и добавочными',
        'fajl': d['istochnik_fajla'], 'zalito': time.strftime('%Y-%m-%d %H:%M'),
        'kompaniy': str(len(d['kompanii'])), 'kontaktov': str(len(d['kontakty'])),
        'version': 'meyer-baza1-' + time.strftime('%Y%m%d%H%M'),
    }.items():
        k.execute('INSERT OR REPLACE INTO import_info (key, value) VALUES (?,?)', (kk, v))
    k.commit()
    print('каталог: компаний %d, контактов %d, людей %d, источников %d' % tuple(
        k.execute('select count(*) from %s' % t).fetchone()[0]
        for t in ('company', 'contact', 'person', 'company_source')))

    # ---------- 2. база продаж: схема текущей, пользователи — только действующие
    star = sqlite3.connect('file:%s?mode=ro' % SALES_OLD, uri=True)
    star.row_factory = sqlite3.Row
    shema_s = [r for r in star.execute(
        "select type, name, sql from sqlite_master where sql is not null and name not like 'sqlite_%' "
        "order by case type when 'table' then 0 when 'index' then 1 else 2 end")]
    lyudi = [dict(r) for r in star.execute('select * from users where is_active=1')]
    star.close()
    s = sqlite3.connect(SALES_NEW)
    for tip, imya, sql in shema_s:
        s.execute(sql)
    for u in lyudi:
        s.execute('INSERT INTO users (%s) VALUES (%s)' % (','.join(u), ','.join('?' * len(u))), list(u.values()))
    s.commit()
    print('продажи: пользователи %s' % [(u['username'], u.get('fio') or '') for u in lyudi])

    # ---------- 3. раздача змейкой по баллу панели
    k.row_factory = sqlite3.Row
    kompanii = [dict(r) for r in k.execute('select * from company')]
    for c in kompanii:
        c['_ball'] = sales.company_score(c)
    kompanii.sort(key=lambda c: (-c['_ball'], -(c['vyruchka_rub'] or 0), c['inn']))
    kol_a = [r[1] for r in s.execute('PRAGMA table_info(company_assignment)')]
    seychas = sales.utcnow()
    itog = {p: [] for p in PRODAVCY}
    for i, c in enumerate(kompanii):
        krug, mesto = divmod(i, len(PRODAVCY))
        kto = PRODAVCY[mesto] if krug % 2 == 0 else PRODAVCY[len(PRODAVCY) - 1 - mesto]
        itog[kto].append(c)
        z = {'inn': c['inn'], 'username': kto, 'assignment_score': c['_ball'],
             'has_phone': c['has_phone'], 'has_purchaser': c['has_purchaser'],
             'has_tech': c['has_tech'], 'has_signal': 0, 'assigned_at': seychas,
             'source_version': 'meyer-baza1', 'assigned_by': 'змейка по баллу'}
        z = {kk: v for kk, v in z.items() if kk in kol_a}
        s.execute('INSERT INTO company_assignment (%s) VALUES (%s)' % (','.join(z), ','.join('?' * len(z))),
                  list(z.values()))
    s.commit()
    imena = {u['username']: u.get('fio') or u['username'] for u in lyudi}
    print()
    print('РАЗДАЧА (змейка по баллу панели):')
    verh = set(c['inn'] for c in kompanii[:16])
    for p in PRODAVCY:
        b = [c['_ball'] for c in itog[p]]
        print('   %-18s компаний %2d, сумма балла %7.1f, средний %5.1f, из 16 сильнейших %d, '
              'лучший %.1f, худший %.1f' % (imena.get(p, p), len(b), sum(b), sum(b) / len(b),
                                          sum(1 for c in itog[p] if c['inn'] in verh), max(b), min(b)))
    k.close()
    s.close()
    raise SystemExit(0)

# ============================================================== ОСНОВНОЙ ХОД (системный питон)
os.makedirs(BEKAP, exist_ok=True)
sreda = dict(os.environ, PYTHONIOENCODING='utf-8')
r = subprocess.run([VENV, os.path.abspath(__file__), '--postroit'], capture_output=True,
                   timeout=900, cwd=KOREN, env=sreda)
print('===== ПОСТРОЕНИЕ =====')
sys.stdout.write(r.stdout.decode('utf-8', 'replace'))
if r.returncode:
    sys.stdout.write('\n--- stderr ---\n' + r.stderr.decode('utf-8', 'replace')[-3000:])
    print('\nПОСТРОЕНИЕ НЕ УДАЛОСЬ — .env и панель не трогаю')
    raise SystemExit(1)

# ---------- 4. .env
nado = sdelano = 0
log = []
shutil.copy2(ENV, os.path.join(BEKAP, '.env'))
NOVOE = {'CENTRIFUGAL_DB': KAT_NEW, 'CENTRO_DB': KAT_NEW, 'PARK_OCHERED_DB': KAT_NEW,
         'CENTRO_SALES_DB': SALES_NEW, 'PARK_OCHERED_SALES_DB': SALES_NEW,
         'PANEL_NAZVANIE': 'Meyer', 'PANEL_PODPIS': 'база продаж',
         'BAZA_NAZVANIE': 'База 1', 'BAZA_OPISANIE': 'ЛПР с мобильными и добавочными'}
stroki = io.open(ENV, encoding='utf-8').read().splitlines()
mesto = {l.split('=', 1)[0].strip(): i for i, l in enumerate(stroki)
         if '=' in l and not l.lstrip().startswith('#')}
dob = []
for kk, v in NOVOE.items():
    if kk in mesto:
        stroki[mesto[kk]] = '%s=%s' % (kk, v)
    else:
        dob.append('%s=%s' % (kk, v))
if dob:
    stroki += ['', '# --- база Мейера и подписи панели (замена базы %s)' % time.strftime('%d.%m.%Y')] + dob
io.open(ENV, 'w', encoding='utf-8').write('\n'.join(stroki) + '\n')
log.append('[ок] .env переключён на meyer_baza1.db и centro_sales_meyer1.db (старые файлы целы)')


def pisat(put, t):
    cel = os.path.join(BEKAP, os.path.relpath(put, KOREN))
    if not os.path.exists(cel):
        os.makedirs(os.path.dirname(cel), exist_ok=True)
        shutil.copy2(put, cel)
    io.open(put, 'w', encoding='utf-8').write(t)


def pravka(put, staro, novo, imya, priznak=None, regex=False):
    global nado, sdelano
    nado += 1
    t = io.open(put, encoding='utf-8').read()
    if priznak and priznak in t:
        sdelano += 1
        log.append('[уже] ' + imya)
        return
    if regex:
        m = list(re.finditer(staro, t, re.S))
        if len(m) != 1:
            log.append('[ЯКОРЬ: %d] %s — не правлю' % (len(m), imya))
            return
        novyy = t[:m[0].start()] + m[0].expand(novo) + t[m[0].end():]
    else:
        if t.count(staro) != 1:
            log.append('[ЯКОРЬ: %d] %s — не правлю' % (t.count(staro), imya))
            return
        novyy = t.replace(staro, novo, 1)
    pisat(put, novyy)
    sdelano += 1
    log.append('[ок] ' + imya)


# ---------- 5. подписи панели из .env
RCS = os.path.join(APP, 'api', 'routes_centro_sales.py')
nado += 1
t = io.open(RCS, encoding='utf-8').read()
if 'globals["panel_nazvanie"]' in t:
    sdelano += 1
    log.append('[уже] глобальные подписи панели')
else:
    pisat(RCS, t.rstrip('\n') + '''


# Название панели и метка загруженной базы — из .env, чтобы следующую базу подписать,
# не трогая шаблоны. Владелец: «название центробежной тоже замени», «отметку База 1,
# под вопросиком расшифровка: ЛПР с мобильными и добавочными».
import os as _os_podpis

templates.env.globals["panel_nazvanie"] = _os_podpis.environ.get("PANEL_NAZVANIE", "Центробежные")
templates.env.globals["panel_podpis"] = _os_podpis.environ.get(
    "PANEL_PODPIS", "база продаж по компрессорному оборудованию")
templates.env.globals["baza_nazvanie"] = _os_podpis.environ.get("BAZA_NAZVANIE", "")
templates.env.globals["baza_opisanie"] = _os_podpis.environ.get("BAZA_OPISANIE", "")
''')
    sdelano += 1
    log.append('[ок] глобальные подписи панели')

SH = os.path.join(T, '_shapka.html')
pravka(SH, '''    <strong>Центробежные</strong>
    <span>база продаж по компрессорному оборудованию</span>''',
       '''    <strong>{{ panel_nazvanie }}{% if baza_nazvanie %} <span class="baza-metka">{{ baza_nazvanie }}<span class="baza-vopros" tabindex="0" title="{{ baza_opisanie }}" aria-label="{{ baza_opisanie }}">?</span></span>{% endif %}</strong>
    <span>{{ panel_podpis }}</span>''', 'шапка: название и метка базы', priznak='baza-metka')
pravka(SH, '<style>.topbar nav a.active',
       '<style>.brand-block .baza-metka{display:inline-flex;align-items:center;gap:5px;margin-left:8px;'
       'padding:2px 8px;border-radius:999px;background:#ffffff1f;border:1px solid #ffffff40;'
       'font-size:12px;font-weight:600;color:#fff;vertical-align:middle}'
       '.brand-block .baza-vopros{display:inline-flex;width:15px;height:15px;border-radius:50%;'
       'align-items:center;justify-content:center;background:#fff;color:#1d2533;font-size:11px;'
       'font-weight:700;cursor:help}</style>\n<style>.topbar nav a.active',
       'шапка: стиль метки', priznak='.baza-vopros{')

for f, staro, novo in (
        ('centro.html', '<title>Центробежные — база продаж</title>', '<title>{{ panel_nazvanie }} — база продаж</title>'),
        ('centro_stats.html', '<title>Статистика — Центробежные</title>', '<title>Статистика — {{ panel_nazvanie }}</title>'),
        ('centro_admin.html', '<title>Распределение — Центробежные</title>', '<title>Распределение — {{ panel_nazvanie }}</title>'),
        ('spisok.html', '<title>Список компаний — обзвон «Центробежные»</title>', '<title>Список компаний — {{ panel_nazvanie }}</title>')):
    pravka(os.path.join(T, f), staro, novo, '%s: заголовок вкладки' % f, priznak='{{ panel_nazvanie }}')
LG = os.path.join(T, 'centro_login.html')
nado += 1
t = io.open(LG, encoding='utf-8').read()
n = t.count('Центробежные')
if n:
    pisat(LG, t.replace('Центробежные', '{{ panel_nazvanie }}'))
    sdelano += 1
    log.append('[ок] centro_login.html: «Центробежные» -> название панели (%d)' % n)
else:
    sdelano += 1
    log.append('[уже] centro_login.html')

# ---------- 6. список: сегмент и ЛПР
SP = os.path.join(T, '_ochered_spisok.html')
pravka(SP, '<th>Выручка</th><th>Машины</th><th>Приговор</th>\n        <th>Контакты</th>',
       '<th>Выручка</th><th>Сегмент</th><th>ЛПР</th>', 'список: шапка таблицы', priznak='<th>ЛПР</th>')
pravka(SP, r'\n        <td>\{\{ c\.tipy_mashin.*?закуп\{% if c\.has_role_phone %\}.*?</td>',
       '''
        <td>{{ (c.segment or '—')|replace(' | ', ', ') }}</td>
        <td>{{ c.lpr_kratko or '—' }}</td>''', 'список: ячейки «Сегмент» и «ЛПР»', priznak='c.lpr_kratko', regex=True)
pravka(SP, "{% if c.status_egrul and (c.status_egrul|upper) != 'ACTIVE' %} · {{ c.status_egrul }}{% endif %}</span></td>",
       "{% if c.status_egrul and (c.status_egrul|upper) != 'ACTIVE' %} · {{ c.status_egrul }}{% endif %}</span>"
       "{% if c.popadanie == 'только доп. ОКВЭД' %} <span class=\"och-tag\" title=\"Сегмент найден только по "
       "дополнительному ОКВЭД\">по доп. ОКВЭД</span>{% endif %}</td>",
       'список: пометка «по доп. ОКВЭД»', priznak='по доп. ОКВЭД</span>')

# ---------- 7. карточка: описание и поля базы
C = os.path.join(T, 'centro.html')
pravka(C, "<p>{{ company.adres or company.address or 'Адрес не указан' }}</p>",
       "{% if company.adres or company.address %}<p>{{ company.adres or company.address }}</p>"
       "{% elif not company.opisanie %}<p>Адрес не указан</p>{% endif %}"
       "{% if company.opisanie %}<p class=\"opisanie\" style=\"max-width:900px\">{{ company.opisanie }}</p>{% endif %}",
       'карточка: описание компании', priznak='class="opisanie"')
pravka(C, "<span><b>Регион</b> {{ company.region or '—' }}</span>",
       "<span><b>Регион</b> {{ company.region or '—' }}</span>"
       "{% if company.segment %}<span><b>Сегмент</b> {{ company.segment|replace(' | ', ', ') }}</span>{% endif %}"
       "{% if company.popadanie %}<span><b>Попадание</b> {{ company.popadanie }}</span>{% endif %}"
       "{% if company.v_baze_obzvona %}<span><b>В базе обзвона</b> {{ company.v_baze_obzvona }}</span>{% endif %}",
       'карточка: сегмент, попадание, база обзвона', priznak='<b>Попадание</b>')

# ---------- 8. пустые компрессорные фильтры
for imya, ot, do, uslovie in (
        ('модель', r'\n  <input name="model" list="model-list-main"', '</datalist>', 'choices.model'),
        ('состояние', r'\n  <select name="sostoyanie"', '</select>', 'choices.sostoyanie'),
        ('приговор', r'\n  <select name="verdikt"', '</select>', 'choices.verdikt'),
        ('под замену', r'\n  <label class="check zamena-check"', '</label>', 'choices.pod_zamenu_n')):
    pravka(C, '(' + ot + '.*?' + re.escape(do) + ')',
           '\n  {%% if %s %%}\\1{%% endif %%}' % uslovie,
           'фильтр «%s» прячется, если пуст' % imya, priznak='{%% if %s %%}' % uslovie, regex=True)

print()
print('===== ПРАВКИ =====')
print('правок внесено: %d из %d' % (sdelano, nado))
for x in log:
    print('   ' + x)
print('бэкап: %s' % BEKAP)

# ---------- перезапуск через загрузчик
p = subprocess.run(['netstat', '-ano'], capture_output=True, timeout=90)
for l in p.stdout.decode('cp866', 'replace').splitlines():
    if (':%d ' % PORT) in l and 'LISTENING' in l.upper():
        subprocess.run(['taskkill', '/PID', l.split()[-1], '/F'], capture_output=True, timeout=60)
time.sleep(2)
lg = io.open(os.path.join(KOREN, 'centro2.log'), 'a', encoding='utf-8', errors='replace')
lg.write('\n===== перезапуск: База 1 Мейера %s =====\n' % time.strftime('%Y-%m-%d %H:%M:%S'))
lg.flush()
subprocess.Popen([VENV, os.path.join(KOREN, 'zapusk.py')], cwd=KOREN, stdout=lg,
                 stderr=subprocess.STDOUT, creationflags=0x00000008 | 0x00000200,
                 close_fds=True, env=sreda)
time.sleep(10)
r = subprocess.run([VENV, os.path.abspath(__file__), '--proverka'], capture_output=True,
                   timeout=1500, cwd=KOREN, env=sreda)
print()
print('===== ПРОВЕРКА =====')
sys.stdout.write(r.stdout.decode('utf-8', 'replace'))
if r.returncode:
    sys.stdout.write('\n--- stderr ---\n' + r.stderr.decode('utf-8', 'replace')[-3000:])
