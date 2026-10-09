# -*- coding: utf-8 -*-
r"""fixH: вид Битрикса в карточке и списке панели Meyer под новую выгрузку сделок 09.10
(владелец: сделки КЦ, СЦ и Meyer по ИНН компании; правка – только шаблоны, код Python не меняется,
перезапуска нет: Jinja перечитывает изменённый шаблон сам).

Что меняется (centro.html и _ochered_spisok.html, по якорям, чтение-правка-запись):
  1. «Битрикс КЦ:» -> «Битрикс:» (в выгрузке теперь и сделки Meyer, и КЦ, и СЦ);
     фильтр «Есть номер в битриксе» -> «Есть в Битриксе» (считает тот же bitrix_kc);
  2. «Клиент Meyer» – если bitrix_klient_meyer (успешная MEYER-Продажа/Постпродажа или любая MEYER-СЦ);
  3. «в работе у КЦ/СЦ: N» – если bitrix_v_rabote (активных сделок КЦ/СЦ сейчас);
  4. дата последней сделки (bitrix_poslednyaya);
  5. подсказка «контакты компании – в карточке Битрикса» (в карточке текстом, в списке – во всплывающей).
Шаблон работает и без новых колонок: всё через company.get(...) с пустым значением по умолчанию.

Режимы:
  --suho      без замка, живые файлы не трогаются: правки – в КОПИИ шаблонов C:\centro2\_bekap\fixH-stage,
              рендер TestClient-ом на копиях баз: (а) каталог как есть, (б) копия каталога с новыми
              колонками и пробными значениями у трёх компаний;
  --primenit  под замком: перечитать живые шаблоны -> правки -> та же проверка на копиях шаблонов ->
              шаблоны на место -> проверка уже живых файлов; провал – СВОИ файлы из копии этого прогона.

    python3 zapusk_na_servere.py fixH_vid.py --suho
    python3 zapusk_na_servere.py fixH_vid.py --primenit
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
KAT = os.path.join(KOREN, 'data', 'meyer_baza1.db')
SALES = os.path.join(KOREN, 'data', 'centro_sales_meyer1.db')
DROP = r'C:\seostat\drop\drop-storage'
PUT = '/obzvon-meyer'
ZAMOK = r'C:\centro2\_zamok.txt'
VREMYA = time.strftime('%Y%m%d-%H%M%S')
STAGE = os.path.join(KOREN, '_bekap', 'fixH-stage')
FAJLY = {'C': os.path.join(T, 'centro.html'), 'L': os.path.join(T, '_ochered_spisok.html')}
STAGE_PUT = {'C': 'centro.html', 'L': '_ochered_spisok.html'}
METKA = 'fixH-bitrix'          # признак, что правка уже стоит (повторный прогон ничего не делает)

if '--vnutri' not in sys.argv and '--render' not in sys.argv:
    r = subprocess.run([VENV, os.path.abspath(__file__), '--vnutri'] + sys.argv[1:], capture_output=True,
                       timeout=1650, cwd=KOREN, env=dict(os.environ, PYTHONIOENCODING='utf-8'))
    sys.stdout.write(r.stdout.decode('utf-8', 'replace')[-5900:])
    if r.returncode:
        sys.stdout.write('\n--- stderr ---\n' + r.stderr.decode('utf-8', 'replace')[-2500:])
    raise SystemExit(r.returncode)

# ====================================================================== правки по якорям
KARTOCHKA_STARO = (
    '<span class="bitrix-galka">✓</span><b>Битрикс КЦ:</b>{% if _бх.klient_sc %}<span class="klient-sc">Клиент СЦ</span>{% endif %}'
    '{% if _бх.sdelok %}<b>{% if _бх.klient_sc %}· {% endif %}{{ _бх.sdelok }}</b>{% elif not _бх.klient_sc %}<b>есть контакт</b>{% endif %}'
    '{% if _бх.voronki %}<span class="bitrix-voronki">{% for v, n in _бх.voronki %}{{ v }}{% if n %} ×{{ n }}{% endif %}'
    '{% if not loop.last %}, {% endif %}{% endfor %}</span>{% endif %}</span>{% endif %}')
KARTOCHKA_NOVO = (
    '<span class="bitrix-galka">✓</span><b>Битрикс:</b>{# ' + METKA + ' #}'
    "{% set _бм = (company.get('bitrix_klient_meyer') or 0)|int %}{% set _бр = (company.get('bitrix_v_rabote') or 0)|int %}"
    '{% if _бм %}<span class="klient-meyer" title="Успешная сделка MEYER-Продажа/Постпродажа или сделка в воронке MEYER-СЦ">Клиент Meyer</span>{% endif %}'
    '{% if _бх.klient_sc %}<span class="klient-sc">Клиент СЦ</span>{% endif %}'
    '{% if _бх.sdelok %}<b>{% if _бх.klient_sc or _бм %}· {% endif %}{{ _бх.sdelok }}</b>{% elif not (_бх.klient_sc or _бм) %}<b>есть контакт</b>{% endif %}'
    '{% if _бх.voronki %}<span class="bitrix-voronki">{% for v, n in _бх.voronki %}{{ v }}{% if n %} ×{{ n }}{% endif %}'
    '{% if not loop.last %}, {% endif %}{% endfor %}</span>{% endif %}'
    '{% if _бр %}<span class="bitrix-v-rabote" title="Активных сделок в воронках КЦ и СЦ сейчас">в работе у КЦ/СЦ: {{ _бр }}</span>{% endif %}'
    "{% if company.get('bitrix_poslednyaya') %}<span class=\"bitrix-data\">последняя сделка {{ company.get('bitrix_poslednyaya') }}</span>{% endif %}"
    '<span class="bitrix-podskazka">контакты компании – в карточке Битрикса</span></span>{% endif %}')

FILTR_STARO = "{% if request.query_params.get('bitrix') == '1' %}checked{% endif %}> Есть номер в битриксе · {{ choices.bitrix_n }}</label>"
FILTR_NOVO = ("{% if request.query_params.get('bitrix') == '1' %}checked{% endif %}> Есть в Битриксе · {{ choices.bitrix_n }}</label>")
FILTR_LABEL_STARO = '<label class="check"><input type="checkbox" name="bitrix" value="1" '
FILTR_LABEL_NOVO = ('<label class="check" title="Есть сделки в Битриксе (КЦ, СЦ или Meyer) по ИНН компании, выгрузка 09.10">'
                    '<input type="checkbox" name="bitrix" value="1" ')

CSS_KARTOCHKA_STARO = ('.klient-sc{display:inline-block;background:#fff4e0;border:1px solid #f3d39b;color:#8a5300;border-radius:4px;\n'
                       '  padding:0 6px;font-weight:700;font-size:12px;white-space:nowrap}\n')
CSS_KARTOCHKA_NOVO = CSS_KARTOCHKA_STARO + (
    '/* ' + METKA + ' 09.10: клиент Meyer, сделки КЦ/СЦ в работе, дата последней сделки, подсказка */\n'
    '.klient-meyer{display:inline-block;background:#e8f0fe;border:1px solid #b6ccf5;color:#1d4ed8;border-radius:4px;\n'
    '  padding:0 6px;font-weight:700;font-size:12px;white-space:nowrap}\n'
    '.bitrix-v-rabote{display:inline-block;color:#8a5300;font-weight:700;white-space:nowrap}\n'
    '.bitrix-data{color:#475467;white-space:nowrap}\n'
    '.bitrix-podskazka{color:#667085;font-style:italic}\n')

SPISOK_STARO = (
    '<span class="bitrix-stroka"><span class="bitrix-galka">✓</span>Битрикс КЦ: {% if _бх.klient_sc %}<span class="klient-sc">Клиент СЦ</span>'
    '{% if _бх.sdelok %} · {% endif %}{% endif %}{{ _бх.sdelok or (\'\' if _бх.klient_sc else \'есть контакт\') }}</span>')
SPISOK_NOVO = (
    "{% set _бм = (c.get('bitrix_klient_meyer') or 0)|int %}{% set _бр = (c.get('bitrix_v_rabote') or 0)|int %}"
    '<span class="bitrix-stroka" title="Контакты компании – в карточке Битрикса{% if c.get(\'bitrix_poslednyaya\') %}; '
    'последняя сделка {{ c.get(\'bitrix_poslednyaya\') }}{% endif %}">{# ' + METKA + ' #}<span class="bitrix-galka">✓</span>Битрикс: '
    '{% if _бм %}<span class="klient-meyer">Клиент Meyer</span>{% if _бх.klient_sc %} {% elif _бх.sdelok %} · {% endif %}{% endif %}'
    '{% if _бх.klient_sc %}<span class="klient-sc">Клиент СЦ</span>{% if _бх.sdelok %} · {% endif %}{% endif %}'
    '{{ _бх.sdelok or (\'\' if (_бх.klient_sc or _бм) else \'есть контакт\') }}'
    '{% if _бр %}<span class="bitrix-v-rabote">в работе у КЦ/СЦ: {{ _бр }}</span>{% endif %}'
    "{% if c.get('bitrix_poslednyaya') %}<span class=\"bitrix-data\">последняя сделка {{ c.get('bitrix_poslednyaya') }}</span>{% endif %}</span>")
CSS_SPISOK_STARO = '.bitrix-stroka .bitrix-galka{width:15px;height:15px;font-size:10px;margin-right:3px}\n'
CSS_SPISOK_NOVO = CSS_SPISOK_STARO + (
    '.bitrix-stroka .bitrix-v-rabote,.bitrix-stroka .bitrix-data{display:block;font-size:11px}\n'
    '.bitrix-stroka .bitrix-data{color:#667085;font-weight:400}\n'
    '.bitrix-stroka .klient-meyer,.bitrix-stroka .klient-sc{font-size:11px}\n')

PRAVKI = [
    ('C', 'карточка: блок Битрикса', KARTOCHKA_STARO, KARTOCHKA_NOVO),
    ('C', 'фильтр: подпись «Есть в Битриксе»', FILTR_STARO, FILTR_NOVO),
    ('C', 'фильтр: подсказка у пункта', FILTR_LABEL_STARO, FILTR_LABEL_NOVO),
    ('C', 'CSS карточки', CSS_KARTOCHKA_STARO, CSS_KARTOCHKA_NOVO),
    ('L', 'список: строка Битрикса', SPISOK_STARO, SPISOK_NOVO),
    ('L', 'CSS списка', CSS_SPISOK_STARO, CSS_SPISOK_NOVO),
]


def primenit(teksty):
    """-> (новые тексты, журнал, всё ли на месте). Уже применённое не трогается (признак METKA/новый текст)."""
    novye = dict(teksty)
    zh, ok = [], True
    for kl, imya, staro, novo in PRAVKI:
        t = novye[kl]
        if t.count(novo) == 1 and (staro not in novo or t.count(staro) == 1):
            zh.append('[уже] ' + imya)
            continue
        n = t.count(staro)
        if n != 1:
            zh.append('[ЯКОРЬ НАЙДЕН %d РАЗ] %s' % (n, imya))
            ok = False
            continue
        novye[kl] = t.replace(staro, novo, 1)
        zh.append('[ок] ' + imya)
    return novye, zh, ok


def prochitat():
    # файлы на сервере с CRLF: текстовый режим даёт \n (якоря с \n), запись текстовым режимом – снова CRLF
    return {k: io.open(p, encoding='utf-8').read() for k, p in FAJLY.items()}


def zapisat(kuda, teksty):
    for k, t in teksty.items():
        p = kuda[k] if isinstance(kuda, dict) else os.path.join(kuda, STAGE_PUT[k])
        os.makedirs(os.path.dirname(p), exist_ok=True)
        io.open(p, 'w', encoding='utf-8').write(t)


def kopiya(src, dst):
    a = sqlite3.connect('file:%s?mode=ro' % src, uri=True)
    b = sqlite3.connect(dst)
    a.backup(b)
    b.close()
    a.close()


# ====================================================================== рендер (отдельный процесс venv)
def render(stage, kat, sales_db, probnye):
    """stage – папка копий шаблонов ('-' – живые); probnye – ИНН с пробными значениями новых колонок."""
    import html as H
    import logging
    import warnings
    warnings.filterwarnings('ignore')
    sys.path.insert(0, KOREN)
    import zapusk  # noqa: F401
    logging.disable(logging.CRITICAL)
    for kk in ('CENTRO_SALES_DB', 'PARK_OCHERED_SALES_DB'):
        os.environ[kk] = sales_db
    for kk in ('CENTRIFUGAL_DB', 'CENTRO_DB', 'PARK_OCHERED_DB'):
        os.environ[kk] = kat
    from app import web
    from app.api import routes_centro_sales as rcs
    from app.obzvon import create_app
    from app.services import centro_catalog as cat
    from fastapi.testclient import TestClient
    from jinja2 import ChoiceLoader, FileSystemLoader
    if stage != '-':
        web.templates.env.loader = ChoiceLoader([FileSystemLoader(stage), web.templates.env.loader])
        if web.templates.env.cache is not None:
            web.templates.env.cache.clear()
    plohih = [0]

    def ok(u, t):
        if not u:
            plohih[0] += 1
        print('   %s %s' % ('ОК ' if u else 'ПЛОХО', t))
        sys.stdout.flush()
    ok(str(cat.db_path()) == kat, 'каталог – копия: %s' % kat)
    k = sqlite3.connect('file:%s?mode=ro' % kat, uri=True)
    k.row_factory = sqlite3.Row
    kol = {r[1] for r in k.execute('PRAGMA table_info(company)')}
    rows = {r['inn']: dict(r) for r in k.execute('SELECT * FROM company')}
    s = sqlite3.connect(sales_db)
    vlad = dict(s.execute('SELECT inn, username FROM company_assignment').fetchall())
    s.close()
    s_bx = sorted(i for i, c in rows.items() if c.get('bitrix_kc'))
    print('   новых колонок в каталоге: %s; компаний с bitrix_kc: %d' % (
        sorted(c for c in kol if c in ('bitrix_klient_meyer', 'bitrix_v_rabote', 'bitrix_poslednyaya')) or 'нет', len(s_bx)))
    vnutr = next(z for z in vars(create_app()).values() if hasattr(z, 'routes') and hasattr(z, 'dependency_overrides'))
    USERS = {'meyer_admin': {'id': 0, 'username': 'meyer_admin', 'role': 'admin', 'is_active': 1}}
    for n_, p in enumerate(('meyer1', 'meyer2', 'meyer3', 'meyer4'), 1):
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
        o = get('/centro')
        t = o.text
        ok(o.status_code == 200, 'админ: главная %s' % o.status_code)
        ok('Битрикс КЦ' not in t and 'Есть номер в битриксе' not in t, 'на главной нет «Битрикс КЦ» и «Есть номер в битриксе»')
        m = re.search(r'name="bitrix" value="1"[^>]*>\s*Есть в Битриксе · (\d+)</label>', t)
        n_f = int(m.group(1)) if m else -1
        n_l = total(get('/centro', params={'bitrix': '1'}).text)
        ok(n_f == n_l == len([i for i in s_bx if i in vlad]),
           'фильтр «Есть в Битриксе»: в подписи %d, находит %d, в каталоге с bitrix_kc (назначенных) %d' % (n_f, n_l, len([i for i in s_bx if i in vlad])))
        n_str = t.count('class="bitrix-stroka"')
        ok(n_str > 0 or not s_bx, 'строк Битрикса в списке первой страницы: %d' % n_str)
        for p in ('meyer1', 'meyer2', 'meyer3', 'meyer4'):
            o = get('/centro', p)
            moi = [i for i in s_bx if vlad.get(i) == p]
            m = re.search(r'Есть в Битриксе · (\d+)</label>', o.text)
            n_p = total(get('/centro', p, params={'bitrix': '1'}).text)
            ok(o.status_code == 200 and m and int(m.group(1)) == n_p == len(moi),
               '%s: главная %s; «Есть в Битриксе» %s, находит %d, своих с bitrix_kc %d' % (p, o.status_code, m.group(1) if m else '?', n_p, len(moi)))
        o = get('/centro/stats')
        ok(o.status_code == 200, 'админ: статистика %s' % o.status_code)
        primery = list(dict.fromkeys(list(probnye) + s_bx[:6] + [i for i in sorted(rows) if not rows[i].get('bitrix_kc')][:2]))
        for inn in primery:
            c = rows[inn]
            o = get('/centro', params={'inn': inn})
            t = o.text
            i0 = t.find('class="hero-badges"')
            hero = t[i0:t.find('</div>', i0)] if i0 >= 0 else ''
            est = bool(c.get('bitrix_kc'))
            usl = o.status_code == 200 and 'Битрикс КЦ' not in t
            if est:
                usl = usl and 'Битрикс:' in hero and 'контакты компании – в карточке Битрикса' in hero
            else:
                usl = usl and 'bitrix-blok' not in hero
            dop = []
            if inn in probnye:
                for ozh in ('Клиент Meyer', 'в работе у КЦ/СЦ: 2', 'последняя сделка 01.10.2026'):
                    dop.append('%s: %s' % (ozh, 'да' if ozh in hero else 'НЕТ'))
                    usl = usl and ozh in hero
            elif est:
                km = int(float(c.get('bitrix_klient_meyer') or 0)) if 'bitrix_klient_meyer' in c else 0
                vr = int(float(c.get('bitrix_v_rabote') or 0)) if 'bitrix_v_rabote' in c else 0
                usl = usl and (('Клиент Meyer' in hero) == bool(km)) and (('в работе у КЦ/СЦ: %d' % vr in hero) if vr else 'в работе у КЦ/СЦ' not in hero)
                if c.get('bitrix_poslednyaya'):
                    usl = usl and ('последняя сделка %s' % c['bitrix_poslednyaya']) in hero
            ok(usl, 'карточка %s (%s), bitrix_kc=%s: %s%s; «%s»' % (
                inn, (c.get('predpriyatie') or '')[:24], c.get('bitrix_kc'), o.status_code, ('; ' + ', '.join(dop)) if dop else '',
                re.sub(r'\s+', ' ', H.unescape(re.sub(r'<[^>]+>', ' ', hero[hero.find('bitrix-blok'):][:900])))[:150] if est else 'без блока'))
            p = vlad.get(inn)
            if p:
                o = get('/centro', p, params={'inn': inn})
                ok(o.status_code == 200, '   своя карточка у %s: %s' % (p, o.status_code))
        # строка списка у пробной компании: поиск по ИНН
        for inn in probnye:
            o = get('/centro', params={'q': inn})
            t = o.text
            i0 = t.find('class="bitrix-stroka"')
            st = t[i0:i0 + 1500] if i0 >= 0 else ''
            ok(o.status_code == 200 and 'Клиент Meyer' in st and 'в работе у КЦ/СЦ: 2' in st and 'Битрикс:' in st,
               'список, поиск %s: строка Битрикса %s' % (inn, re.sub(r'\s+', ' ', H.unescape(re.sub(r'<[^>]+>', ' ', st[:700])))[:140]))
    print('ПЛОХИХ ПРОВЕРОК: %d' % plohih[0])
    return plohih[0]


if '--render' in sys.argv:
    i = sys.argv.index('--render')
    stage, kat, sales_db = sys.argv[i + 1:i + 4]
    probnye = [x for x in sys.argv[i + 4].split(',') if x] if len(sys.argv) > i + 4 else []
    raise SystemExit(1 if render(stage, kat, sales_db, probnye) else 0)


def proverit_vse(stage, papka, metka):
    """Два рендера: (а) каталог как есть; (б) копия каталога с новыми колонками и пробными значениями."""
    ts, tk, tk2 = (os.path.join(papka, x) for x in ('t_sales.db', 't_kat.db', 't_kat_novye.db'))
    kopiya(SALES, ts)
    kopiya(KAT, tk)
    kopiya(KAT, tk2)
    k = sqlite3.connect(tk2)
    kol = {r[1] for r in k.execute('PRAGMA table_info(company)')}
    for c, tip in (('bitrix_klient_meyer', 'INTEGER'), ('bitrix_v_rabote', 'INTEGER'), ('bitrix_poslednyaya', 'TEXT')):
        if c not in kol:
            k.execute('ALTER TABLE company ADD COLUMN %s %s' % (c, tip))
    probnye = [r[0] for r in k.execute('SELECT inn FROM company WHERE bitrix_kc ORDER BY inn LIMIT 2')]
    probnye += [r[0] for r in k.execute('SELECT inn FROM company WHERE NOT bitrix_kc ORDER BY inn LIMIT 1')]
    for inn in probnye:
        k.execute("UPDATE company SET bitrix_kc=1, bitrix_klient_meyer=1, bitrix_v_rabote=2, bitrix_poslednyaya='01.10.2026', "
                  "bitrix_kc_info=COALESCE(bitrix_kc_info, 'сделок 1: MEYER-СЦ ×1') WHERE inn=?", (inn,))
    k.commit()
    k.close()
    vyvod, plohih = '', 0
    for nazv, kat, pr in (('каталог как есть', tk, ''), ('копия каталога с новыми колонками, пробные: ' + ','.join(probnye), tk2, ','.join(probnye))):
        r = subprocess.run([VENV, os.path.abspath(__file__), '--render', stage, kat, ts, pr], capture_output=True, timeout=900,
                           cwd=KOREN, env=dict(os.environ, PYTHONIOENCODING='utf-8'))
        v = r.stdout.decode('utf-8', 'replace') + (r.stderr.decode('utf-8', 'replace')[-2500:] if r.returncode else '')
        vyvod += '----- %s: %s\n%s\n' % (metka, nazv, v)
        if r.returncode or 'ПЛОХИХ ПРОВЕРОК: 0' not in v:
            plohih += 1
    io.open(os.path.join(DROP, 'fixH-vid-%s-%s.txt' % (metka, VREMYA)), 'w', encoding='utf-8').write(vyvod)
    for f in (ts, tk, tk2):
        try:
            os.remove(f)
        except OSError:
            pass
    return plohih == 0, vyvod


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


PAPKA = os.path.join(KOREN, '_bekap', 'fixH-vid-' + VREMYA)
os.makedirs(PAPKA, exist_ok=True)
if '--suho' in sys.argv:
    teksty = prochitat()
    novye, zh, vse_ok = primenit(teksty)
    print('\n'.join('   ' + x for x in zh))
    if not vse_ok:
        print('ЯКОРЯ НЕ НАЙДЕНЫ – ничего не делаю')
        raise SystemExit(4)
    if os.path.isdir(STAGE):
        shutil.rmtree(STAGE, ignore_errors=True)
    zapisat(STAGE, novye)
    good, vyvod = proverit_vse(STAGE, PAPKA, 'suho')
    print(vyvod[-4800:])
    print('СУХОЙ ПРОГОН: %s (живые файлы не тронуты)' % ('ОК' if good else 'ЕСТЬ ПЛОХИЕ'))
    raise SystemExit(0)

if '--primenit' in sys.argv:
    vzyat_zamok('fixH (вид Битрикса: centro.html, _ochered_spisok.html)')
    try:
        teksty = prochitat()
        for k_, p in FAJLY.items():
            shutil.copy2(p, os.path.join(PAPKA, STAGE_PUT[k_]))
        novye, zh, vse_ok = primenit(teksty)
        print('\n'.join('   ' + x for x in zh))
        if not vse_ok:
            print('ЯКОРЯ НЕ НАЙДЕНЫ – живые файлы не тронуты')
            raise SystemExit(4)
        izm = {k_: novye[k_] for k_ in novye if novye[k_] != teksty[k_]}
        if not izm:
            print('правки уже стоят – файлы не меняю')
        if os.path.isdir(STAGE):
            shutil.rmtree(STAGE, ignore_errors=True)
        zapisat(STAGE, novye)
        good, vyvod = proverit_vse(STAGE, PAPKA, 'stage')
        print(vyvod[-2500:])
        if not good:
            print('ПРОВЕРКА НА КОПИЯХ ШАБЛОНОВ НЕ ПРОШЛА – живые файлы не тронуты')
            raise SystemExit(5)
        # на место: только если живой файл не менялся за время прогона
        for k_ in izm:
            if io.open(FAJLY[k_], encoding='utf-8').read() != teksty[k_]:
                print('ФАЙЛ %s ИЗМЕНИЛСЯ ЗА ВРЕМЯ ПРОГОНА – не пишу' % FAJLY[k_])
                raise SystemExit(6)
        zapisat(FAJLY, izm)
        good, vyvod = proverit_vse('-', PAPKA, 'zhivye')
        print(vyvod[-3000:])
        if not good:
            for k_ in izm:
                shutil.copy2(os.path.join(PAPKA, STAGE_PUT[k_]), FAJLY[k_])
            print('ПРОВЕРКА ЖИВЫХ ФАЙЛОВ НЕ ПРОШЛА – свои файлы возвращены из копии %s' % PAPKA)
            raise SystemExit(7)
        print('ПРИМЕНЕНО: %s; копия прежних файлов: %s (перезапуск не нужен – Jinja перечитывает шаблон)' % (
            ', '.join(STAGE_PUT[k_] for k_ in izm) or 'ничего', PAPKA))
    finally:
        otdat_zamok()
