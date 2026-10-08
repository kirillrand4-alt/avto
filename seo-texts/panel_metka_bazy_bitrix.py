# -*- coding: utf-8 -*-
"""Метка источника у КАЖДОЙ компании + зелёная галочка «Есть контакт в битриксе КЦ».

Владелец: «метку База 1, 2, 3 надо напротив строки с самой компанией, потому что база
то одна будет, просто наполнится из разных источников». Значит метка — свойство
компании, а не панели: колонки bazy / bazy_opisanie в каталоге. Через « | », потому что
одна компания может прийти из нескольких источников — источники накапливаются, а не
заменяются (правило владельца).

Галочка: «в списке добавь галочку зелёную, при наведении “Есть контакт в битриксе КЦ”».
Справочник из выгрузки сделок Битрикса (deals_inn_4.csv): 24 755 разных ИНН. ИНН из 9 и
11 цифр дополнены нулём спереди — Excel съедает ведущий ноль у регионов 01–09; без этого
одна из компаний Базы 1 не находилась. Справочник кладётся в C:\\centro2\\data\\, чтобы
галочки ставились и следующим базам.

Плюс: фильтр «Под замену» прячется, когда пуст (прошлая правка его пропустила: внутри
метки уже было {% if choices.pod_zamenu_n %}, и проверка «уже сделано» сработала ложно).
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
T = os.path.join(KOREN, 'app', 'templates')
ENV = os.path.join(KOREN, '.env')
PORT = 8016
PUT = '/obzvon-meyer'
KAT = os.path.join(DATA, 'meyer_baza1.db')
BITRIX_SRC = r'C:\seostat\drop\drop-storage\bitrix-kc.json'
BITRIX = os.path.join(DATA, 'bitrix_kc_inn.json')
BEKAP = os.path.join(KOREN, '_bekap', time.strftime('metka-bitrix-%Y%m%d-%H%M%S'))

if '--proverka' in sys.argv:
    sys.path.insert(0, KOREN)
    import zapusk  # noqa: F401
    import logging
    import warnings
    warnings.filterwarnings('ignore')
    logging.disable(logging.CRITICAL)
    from app.api import routes_centro_sales as rcs
    from app.obzvon import create_app
    from fastapi.testclient import TestClient

    vnutr = next(z for z in vars(create_app()).values()
                 if hasattr(z, 'routes') and hasattr(z, 'dependency_overrides'))
    vnutr.dependency_overrides[rcs.current_user] = lambda: {
        'id': 0, 'username': 'meyer_admin', 'role': 'admin', 'is_active': 1}
    c = sqlite3.connect(KAT)
    ozh_bitrix = {r[0] for r in c.execute('select inn from company where bitrix_kc > 0')}
    plohih = 0

    def proverit(u, t):
        global plohih
        if not u:
            plohih += 1
        print('   %s %s' % ('ОК ' if u else 'ПЛОХО', t))

    with TestClient(vnutr) as k:
        o = k.get(PUT + '/centro?size=100')
    t = o.text
    sh = re.search(r'<header class="topbar">.*?</header>', t, re.S).group(0)
    proverit('База 1' not in sh and 'baza-metka' not in sh, 'в шапке метки базы больше нет')
    tab = t.split('<table class="och-tab">')[1].split('</table>')[0]
    metki = re.findall(r'<span class="baza-metka">([^<]+)<span class="baza-vopros"[^>]*title="([^"]*)"', tab)
    proverit(len(metki) == 65 and all(m[0] == 'База 1' and 'мобильными и добавочными' in m[1] for m in metki),
             'метка «База 1 ?» в строке у всех: %d из 65, подсказка %r' % (len(metki), metki[0][1] if metki else None))
    galki = re.findall(r'<tr data-href="[^"]*inn=(\d+)[^"]*">(?:(?!</tr>).)*?class="bitrix-galka"[^>]*title="([^"]*)"', tab, re.S)
    proverit({g[0] for g in galki} == ozh_bitrix,
             'зелёных галочек %d, ожидалось %d (ИНН совпадают: %s)'
             % (len(galki), len(ozh_bitrix), {g[0] for g in galki} == ozh_bitrix))
    if galki:
        print('      подсказка: %r' % galki[0][1].replace('&#10;', ' / '))
    proverit('name="pod_zamenu"' not in t.split('<dialog')[0], '«Под замену» в строке фильтров спрятан')
    s_opis = c.execute("select count(*) from company where coalesce(opisanie,'')<>''").fetchone()[0]
    n_opis = len(re.findall(r'<div class="komp-opis"', tab))
    proverit(n_opis == s_opis, 'описание с сайта в строке: %d (в базе с описанием %d)' % (n_opis, s_opis))
    lpr = re.findall(r'<span title="[^"]*">([^<]*)</span></td>', tab)
    proverit(lpr and not any(re.search(r'\+7|\d{3}-\d{2}', x) for x in lpr),
             'в «ЛПР» только роли, без номеров: например %r' % (lpr[:3],))
    inn_g = sorted(ozh_bitrix)[0] if ozh_bitrix else ''
    with TestClient(vnutr) as k:
        o = k.get(PUT + '/centro?inn=' + inn_g)
    proverit(o.status_code == 200 and 'baza-metka' in o.text and 'bitrix-galka' in o.text,
             'карточка %s: метка базы и галочка Битрикса есть' % inn_g)
    print()
    print('ПЛОХИХ ПРОВЕРОК: %d' % plohih)
    raise SystemExit(0)

os.makedirs(BEKAP, exist_ok=True)
log = []
nado = sdelano = 0

# ---------------------------------------------------------- 1. справочник и каталог
shutil.copy2(BITRIX_SRC, BITRIX)
bitrix = json.load(io.open(BITRIX, encoding='utf-8'))
shutil.copy2(KAT, os.path.join(BEKAP, os.path.basename(KAT)))
k = sqlite3.connect(KAT)
kol = {r[1] for r in k.execute('PRAGMA table_info(company)')}
for imya, opr in (('bazy', 'TEXT'), ('bazy_opisanie', 'TEXT'),
                  ('bitrix_kc', 'INTEGER NOT NULL DEFAULT 0'), ('bitrix_kc_info', 'TEXT'),
                  ('lpr_roli', 'TEXT')):
    if imya not in kol:
        k.execute('ALTER TABLE company ADD COLUMN %s %s' % (imya, opr))
# Роли ЛПР для узкой колонки списка («про ЛПР можешь просто роль написать, чтобы сузить
# столбец»). Порядок — как контакты залиты: лучший первым. Повторы роли не дублируются.
roli = {}
for inn, rol in k.execute("select inn, role from contact where coalesce(role,'')<>'' order by id"):
    spisok = roli.setdefault(inn, [])
    if rol not in spisok:
        spisok.append(rol)
for inn, spisok in roli.items():
    k.execute('UPDATE company SET lpr_roli=? WHERE inn=?', (', '.join(spisok), inn))
k.execute("UPDATE company SET bazy='База 1', bazy_opisanie='ЛПР с мобильными и добавочными' "
          "WHERE COALESCE(bazy,'')=''")
nashli = 0
for (inn,) in k.execute('select inn from company').fetchall():
    x = bitrix.get(inn)
    if x:
        nashli += 1
        info = 'сделок %d: %s' % (x['sdelok'], ', '.join(
            '%s ×%d' % (v, n) for v, n in sorted(x['voronki'].items(), key=lambda p: -p[1])))
        k.execute('UPDATE company SET bitrix_kc=?, bitrix_kc_info=? WHERE inn=?', (x['sdelok'], info, inn))
k.execute("INSERT OR REPLACE INTO import_info (key, value) VALUES ('bitrix_kc', ?)",
          ('deals_inn_4.csv: %d ИНН, совпало с базой %d, %s' % (len(bitrix), nashli, time.strftime('%Y-%m-%d %H:%M')),))
k.commit()
k.close()
log.append('[ок] каталог: метка «База 1» у всех, Битрикс КЦ совпал у %d компаний' % nashli)


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


# ---------------------------------------------------------- 2. шапка: метку убрать
SH = os.path.join(T, '_shapka.html')
pravka(SH, '{% if baza_nazvanie %} <span class="baza-metka">{{ baza_nazvanie }}<span class="baza-vopros" tabindex="0" title="{{ baza_opisanie }}" aria-label="{{ baza_opisanie }}">?</span></span>{% endif %}',
       '', 'шапка: метка базы убрана (она у компании, не у панели)', priznak='{#метка-базы-у-компании#}')
# общие стили метки и галочки — шапка подключается на всех страницах
pravka(SH, re.escape('<style>.brand-block .baza-metka{') + r'.*?</style>',
       '<style>{#метка-базы-у-компании#}'
       '.baza-metka{display:inline-flex;align-items:center;gap:4px;margin-left:6px;padding:0 3px 0 8px;'
       'border-radius:999px;background:#eef0fb;border:1px solid #d5d9f3;color:#3b3f8f;font-size:11px;'
       'font-weight:600;vertical-align:middle;white-space:nowrap;line-height:18px}'
       '.baza-vopros{display:inline-flex;width:14px;height:14px;border-radius:50%;align-items:center;'
       'justify-content:center;background:#3b3f8f;color:#fff;font-size:10px;font-weight:700;cursor:help}'
       '.bitrix-galka{display:inline-flex;width:18px;height:18px;border-radius:50%;align-items:center;'
       'justify-content:center;background:#1f9d55;color:#fff;font-size:12px;font-weight:700;cursor:help;'
       'margin-right:5px;vertical-align:middle}</style>',
       'стили метки базы и галочки — на всех страницах', priznak='.bitrix-galka{', regex=True)

nado += 1
stroki = io.open(ENV, encoding='utf-8').read().splitlines()
ostalos = [l for l in stroki if not re.match(r'^\s*BAZA_(NAZVANIE|OPISANIE)\s*=', l)]
if len(ostalos) != len(stroki):
    shutil.copy2(ENV, os.path.join(BEKAP, '.env'))
    io.open(ENV, 'w', encoding='utf-8').write('\n'.join(ostalos) + '\n')
sdelano += 1
log.append('[ок] .env: BAZA_NAZVANIE/BAZA_OPISANIE убраны (метка теперь в данных компании)')

# ---------------------------------------------------------- 3. список
METKA = ('{% if c.bazy %}{% set _op = (c.bazy_opisanie or \'\').split(\' | \') %}'
         '{% for b in c.bazy.split(\' | \') %}<span class="baza-metka">{{ b }}<span class="baza-vopros" '
         'tabindex="0" title="{{ _op[loop.index0] if loop.index0 < _op|length else \'\' }}">?</span></span>'
         '{% endfor %}{% endif %}')
SP = os.path.join(T, '_ochered_spisok.html')
# Ячейка «Компания»: слева название, метка базы, ИНН и регион; справа — описание с сайта
# («сюда описание с сайта про компанию помести»), три строки, целиком при наведении.
pravka(SP, r'<td><a class="nazv" href="\{\{ ssylka \}\}">.*?</td>',
       '<td><div class="komp-yach"><div class="komp-lev">'
       '<a class="nazv" href="{{ ssylka }}">{{ c.predpriyatie or c.name_short or c.inn }}</a>' + METKA +
       '\n          <br><span class="tiho">{{ c.inn }}{% if c.region %} · {{ c.region }}{% endif %}'
       "{% if c.status_egrul and (c.status_egrul|upper) != 'ACTIVE' %} · {{ c.status_egrul }}{% endif %}</span>"
       "{% if c.popadanie == 'только доп. ОКВЭД' %} <span class=\"och-tag\" title=\"Сегмент найден только по "
       'дополнительному ОКВЭД">по доп. ОКВЭД</span>{% endif %}</div>'
       '\n          {% if c.opisanie %}<div class="komp-opis" title="{{ c.opisanie }}">{{ c.opisanie }}</div>{% endif %}'
       '</div></td>',
       'список: метка базы и описание с сайта в ячейке компании', priznak='class="komp-yach"', regex=True)
pravka(SP, "<td>{{ c.lpr_kratko or '—' }}</td>",
       "<td>{% if c.bitrix_kc %}<span class=\"bitrix-galka\" tabindex=\"0\" "
       "title=\"Есть контакт в битриксе КЦ&#10;{{ c.bitrix_kc_info }}\">✓</span>{% endif %}"
       "<span title=\"{{ c.lpr_kratko or '' }}\">{{ c.lpr_roli or c.lpr_kratko or '—' }}</span></td>",
       'список: в «ЛПР» только роли (+ зелёная галочка Битрикса КЦ)', priznak='bitrix-galka')
pravka(SP, '.och-stranicy{display:flex;',
       '.komp-yach{display:flex;gap:16px;align-items:flex-start}\n'
       '.komp-lev{flex:0 0 260px;min-width:0}\n'
       '.komp-opis{flex:1 1 auto;max-width:460px;color:var(--muted);font-size:12px;line-height:1.4;\n'
       '  display:-webkit-box;-webkit-line-clamp:3;-webkit-box-orient:vertical;overflow:hidden}\n'
       '.och-stranicy{display:flex;',
       'список: стили ячейки компании', priznak='.komp-yach{')

# ---------------------------------------------------------- 4. карточка
C = os.path.join(T, 'centro.html')
pravka(C, '<div class="hero-badges">',
       '<div class="hero-badges">'
       + METKA.replace('c.bazy', 'company.bazy')
       + '{% if company.bitrix_kc %}<span class="tag" style="background:#e8f6ee;border-color:#b7e1c7;color:#17663a" '
         'title="{{ company.bitrix_kc_info }}"><span class="bitrix-galka">✓</span>Есть контакт в битриксе КЦ</span>{% endif %}',
       'карточка: метка базы и Битрикс КЦ', priznak='company.bitrix_kc')

# ---------------------------------------------------------- 5. «Под замену»
pravka(C, r'(\n  <label class="check zamena-check".*?</label>)',
       '\n  {% if choices.pod_zamenu_n %}{# под замену: прячется, если пусто #}\\1{% endif %}',
       'фильтр «Под замену» прячется, если пуст', priznak='{# под замену: прячется', regex=True)

print('правок внесено: %d из %d' % (sdelano, nado))
for x in log:
    print('   ' + x)
print('бэкап: %s' % BEKAP)

# ---------------------------------------------------------- перезапуск и проверка
sreda = dict(os.environ, PYTHONIOENCODING='utf-8')
p = subprocess.run(['netstat', '-ano'], capture_output=True, timeout=90)
for l in p.stdout.decode('cp866', 'replace').splitlines():
    if (':%d ' % PORT) in l and 'LISTENING' in l.upper():
        subprocess.run(['taskkill', '/PID', l.split()[-1], '/F'], capture_output=True, timeout=60)
time.sleep(2)
lg = io.open(os.path.join(KOREN, 'centro2.log'), 'a', encoding='utf-8', errors='replace')
lg.write('\n===== перезапуск: метка базы у компании, Битрикс КЦ %s =====\n' % time.strftime('%Y-%m-%d %H:%M:%S'))
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
