# -*- coding: utf-8 -*-
r"""fixK: показ данных базы MEYER-7 в карточке панели Meyer (только шаблон centro.html, код Python не меняется,
перезапуска нет: Jinja перечитывает изменённый шаблон сам).

Что добавляется (по якорям, чтение-правка-запись под замком):
  1. в блоке «О компании» (макрос opis_kompanii – на ноутбуке в шапке, на телефоне после «Контактов»):
     «Паспорт компании» – сырьё, контроль качества, оборудование и линии, упаковка и фасовка, экспорт, масштаб
     (мощности уже показываются строкой «Мощности»); «Ревизия сборки» – пометка профиля («низкий приоритет»,
     «проверить», «сайт общий с …», список «не покупатель» и вердикт оценщика); свёрнутое «Сборка MEYER-7: сайт и
     поиск» – чей сайт, как найден ИНН, сомнения опровергателя, пояснение агента, откуда компания, запрос,
     директор по базе обзвона, «есть в нашей базе», ЛПР и письмо по сборке, источник выручки, провенанс;
  2. в строке сведений – «Сегмент MEYER-7» (сегмент сборки; шкала панели – в «Сегмент»).
Шаблон работает и без новых колонок: всё через company.get(...) (пусто – блока нет).

    python3 zapusk_na_servere.py fixK_vid.py --suho        # копии шаблонов и баз, живые не трогаются
    python3 zapusk_na_servere.py fixK_vid.py --primenit    # под замком
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
STAGE = os.path.join(KOREN, '_bekap', 'fixK-stage')
FAJLY = {'C': os.path.join(T, 'centro.html')}
STAGE_PUT = {'C': 'centro.html'}
METKA = 'fixK-pasport'
PRODAVCY = ['meyer1', 'meyer2', 'meyer3', 'meyer4', 'meyer5', 'meyer6', 'meyer7', 'meyer8', 'meyer9']

if '--vnutri' not in sys.argv and '--render' not in sys.argv:
    r = subprocess.run([VENV, os.path.abspath(__file__), '--vnutri'] + sys.argv[1:], capture_output=True,
                       timeout=1650, cwd=KOREN, env=dict(os.environ, PYTHONIOENCODING='utf-8'))
    sys.stdout.write(r.stdout.decode('utf-8', 'replace')[-5900:])
    if r.returncode:
        sys.stdout.write('\n--- stderr ---\n' + r.stderr.decode('utf-8', 'replace')[-2500:])
    raise SystemExit(r.returncode)

# ====================================================================== правки по якорям
OPIS_STARO = ('{% if company.moshchnosti %}<p class="opis-dop"><b>Мощности:</b> {{ company.moshchnosti }}</p>{% endif %}')
OPIS_NOVO = OPIS_STARO + (
    '{# ' + METKA + ' 13.10: паспорт и ревизия базы MEYER-7 #}'
    "{% set _пасп = [] %}{% for _н, _к in [('Сырьё', 'pasport_syrye'), ('Контроль качества', 'pasport_kachestvo'), "
    "('Оборудование и линии', 'pasport_oborudovanie'), ('Упаковка и фасовка', 'pasport_upakovka'), ('Экспорт', 'pasport_eksport'), "
    "('Масштаб', 'pasport_masshtab')] %}{% if company.get(_к) %}{% set _ = _пасп.append((_н, company.get(_к))) %}{% endif %}{% endfor %}"
    '{% if _пасп %}<div class="pasport-k"><b class="pasport-zag">Паспорт компании</b><dl>{% for _н, _з in _пасп %}'
    '<div><dt>{{ _н }}</dt><dd>{{ _з }}</dd></div>{% endfor %}</dl></div>{% endif %}'
    "{% if company.get('reviziya_profil') %}<p class=\"reviziya-k\" title=\"Пометка сборки MEYER-7 о профиле компании: "
    "проверить перед звонком\"><b>Ревизия сборки:</b> {{ company.get('reviziya_profil') }}</p>{% endif %}"
    "{% set _сб = [] %}{% for _н, _к in [('Чей сайт', 'sayt_chey'), ('ИНН найден по сайту', 'inn_nayden_po_saytu'), "
    "('Сомнение в сайте', 'spornyy_sayt'), ('Пояснение агента', 'poyasnenie_agenta'), ('Откуда компания', 'otkuda_kompaniya'), "
    "('Найдена по запросу', 'naydena_po_zaprosu'), ('Директор по базе обзвона', 'baza_obzvona_direktor'), "
    "('Наша база', 'v_nashey_baze'), ('ЛПР по сборке', 'lpr_sborki'), ('Письмо по сборке', 'pismo_sborki'), "
    "('Контактов в сборке', 'kontaktov_sborki'), ('Выручка: откуда', 'vyruchka_istochnik'), ('Статус проверен', 'status_proveren'), "
    "('Источники', 'istochniki')] %}{% if company.get(_к) %}{% set _ = _сб.append((_н, company.get(_к))) %}{% endif %}{% endfor %}"
    "{% if company.get('segment_meyer7') and _сб %}<details class=\"sborka-k\"><summary>Сборка MEYER-7: сайт и поиск</summary>"
    '<dl>{% for _н, _з in _сб %}<div><dt>{{ _н }}</dt><dd>{{ _з }}</dd></div>{% endfor %}</dl></details>{% endif %}')

SEG_STARO = '{% if company.otrasl %}<span><b>Отрасль</b> {{ company.otrasl }}</span>{% endif %}'
SEG_NOVO = SEG_STARO + ("{% if company.get('segment_meyer7') %}<span title=\"Сегмент по сборке MEYER-7 (13.10); шкала панели – "
                        "«Сегмент»\"><b>Сегмент MEYER-7</b> {{ company.get('segment_meyer7') }}</span>{% endif %}")

CSS_STARO = '.opis-dop{margin:4px 0 0;font-size:13px;color:var(--navy);max-width:900px}\n'
CSS_NOVO = CSS_STARO + (
    '/* ' + METKA + ' 13.10: паспорт компании, ревизия и сведения сборки MEYER-7 */\n'
    '.pasport-k{margin:8px 0 0;max-width:900px;border:1px solid #d0d7e2;border-radius:6px;padding:6px 10px;background:#f8fafc}\n'
    '.pasport-k .pasport-zag{display:block;font-size:13px;color:var(--navy);margin-bottom:2px}\n'
    '.pasport-k dl,.sborka-k dl{margin:0;display:grid;grid-template-columns:max-content 1fr;gap:2px 10px;font-size:13px}\n'
    '.pasport-k dl>div,.sborka-k dl>div{display:contents}\n'
    '.pasport-k dt,.sborka-k dt{color:#475467;font-weight:600}\n'
    '.pasport-k dd,.sborka-k dd{margin:0;overflow-wrap:anywhere}\n'
    '.reviziya-k{margin:6px 0 0;font-size:13px;color:#8a5300;max-width:900px}\n'
    '.sborka-k{margin:6px 0 0;max-width:900px;font-size:13px}\n'
    '.sborka-k summary{cursor:pointer;color:#475467}\n'
    '@media (max-width:600px){.pasport-k dl,.sborka-k dl{grid-template-columns:1fr}.pasport-k dt,.sborka-k dt{margin-top:4px}}\n')

PRAVKI = [
    ('C', 'карточка: паспорт, ревизия, сведения сборки', OPIS_STARO, OPIS_NOVO),
    ('C', 'карточка: «Сегмент MEYER-7» в строке сведений', SEG_STARO, SEG_NOVO),
    ('C', 'CSS паспорта', CSS_STARO, CSS_NOVO),
]


def primenit(teksty):
    novye = dict(teksty)
    zh, ok = [], True
    for kl, imya, staro, novo in PRAVKI:
        t = novye[kl]
        if t.count(novo) == 1:
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
    ok(str(cat.db_path()) == kat, 'каталог – копия')
    k = sqlite3.connect('file:%s?mode=ro' % kat, uri=True)
    k.row_factory = sqlite3.Row
    kol = {r[1] for r in k.execute('PRAGMA table_info(company)')}
    rows = {r['inn']: dict(r) for r in k.execute('SELECT * FROM company')}
    s = sqlite3.connect(sales_db)
    vlad = dict(s.execute('SELECT inn, username FROM company_assignment').fetchall())
    s.close()
    s_p = sorted(i for i, c in rows.items() if any(c.get(x) for x in ('pasport_syrye', 'pasport_kachestvo', 'pasport_oborudovanie',
                                                                        'pasport_upakovka', 'pasport_eksport', 'pasport_masshtab')))
    print('   колонок паспорта в каталоге: %s; компаний с паспортом: %d' % (
        'есть' if 'pasport_syrye' in kol else 'нет', len(s_p)))
    vnutr = next(z for z in vars(create_app()).values() if hasattr(z, 'routes') and hasattr(z, 'dependency_overrides'))
    USERS = {'meyer_admin': {'id': 0, 'username': 'meyer_admin', 'role': 'admin', 'is_active': 1}}
    for n_, p in enumerate(PRODAVCY, 1):
        USERS[p] = {'id': n_, 'username': p, 'role': 'sales', 'is_active': 1}
    kto = {'u': USERS['meyer_admin']}
    vnutr.dependency_overrides[rcs.current_user] = lambda: kto['u']
    with TestClient(vnutr) as kl:
        def get(u, kak='meyer_admin', **kw):
            kto['u'] = USERS[kak]
            return kl.get(PUT + u, follow_redirects=False, **kw)
        for nazv, u in (('главная', '/centro'), ('статистика', '/centro/stats')):
            o = get(u)
            ok(o.status_code == 200, 'админ: %s %s' % (nazv, o.status_code))
        for p in PRODAVCY:
            o = get('/centro', p)
            ok(o.status_code in (200,), '%s: главная %s' % (p, o.status_code))
        bez = [i for i in sorted(rows) if i not in s_p][:3]
        primery = list(dict.fromkeys(list(probnye) + s_p[:8] + bez))
        for inn in primery:
            c = rows[inn]
            o = get('/centro', params={'inn': inn})
            t = o.text
            est_p = inn in s_p or inn in probnye
            usl = o.status_code == 200 and (('Паспорт компании' in t) == est_p)
            dop = []
            if c.get('reviziya_profil') or inn in probnye:
                usl = usl and 'Ревизия сборки:' in t
                dop.append('ревизия')
            if c.get('segment_meyer7') or inn in probnye:
                usl = usl and 'Сегмент MEYER-7' in t and 'Сборка MEYER-7: сайт и поиск' in t
                dop.append('сегмент и сведения сборки')
            i0 = t.find('class="pasport-k"')
            ok(usl, 'карточка %s (%s): %s; паспорт %s%s; «%s»' % (
                inn, (c.get('predpriyatie') or '')[:24], o.status_code, 'есть' if 'Паспорт компании' in t else 'нет',
                (' + ' + ', '.join(dop)) if dop else '',
                re.sub(r'\s+', ' ', H.unescape(re.sub(r'<[^>]+>', ' ', t[i0:i0 + 600])))[:120] if i0 >= 0 else ''))
            p = vlad.get(inn)
            if p:
                o = get('/centro', p, params={'inn': inn})
                ok(o.status_code == 200 and (('Паспорт компании' in o.text) == est_p), '   своя карточка у %s: %s' % (p, o.status_code))
    print('ПЛОХИХ ПРОВЕРОК: %d' % plohih[0])
    return plohih[0]


if '--render' in sys.argv:
    i = sys.argv.index('--render')
    stage, kat, sales_db = sys.argv[i + 1:i + 4]
    probnye = [x for x in sys.argv[i + 4].split(',') if x] if len(sys.argv) > i + 4 else []
    raise SystemExit(1 if render(stage, kat, sales_db, probnye) else 0)


def proverit_vse(stage, papka, metka):
    """(а) каталог как есть; (б) копия каталога с колонками паспорта и пробными значениями у двух компаний."""
    ts, tk, tk2 = (os.path.join(papka, x) for x in ('t_sales.db', 't_kat.db', 't_kat_novye.db'))
    kopiya(SALES, ts)
    kopiya(KAT, tk)
    kopiya(KAT, tk2)
    k = sqlite3.connect(tk2)
    kol = {r[1] for r in k.execute('PRAGMA table_info(company)')}
    for c in ('pasport_syrye', 'pasport_kachestvo', 'pasport_oborudovanie', 'pasport_upakovka', 'pasport_eksport',
              'pasport_masshtab', 'reviziya_profil', 'segment_meyer7', 'sayt_chey', 'istochniki'):
        if c not in kol:
            k.execute('ALTER TABLE company ADD COLUMN %s TEXT' % c)
    probnye = [r[0] for r in k.execute("SELECT inn FROM company WHERE TRIM(COALESCE(segment_meyer7,''))='' ORDER BY inn LIMIT 2")]
    for inn in probnye:
        k.execute("UPDATE company SET pasport_syrye='пробное сырьё', pasport_masshtab='пробный масштаб', "
                  "reviziya_profil='пробная ревизия', segment_meyer7='пробный сегмент', "
                  "sayt_chey=COALESCE(sayt_chey, 'пробно') WHERE inn=?", (inn,))
    k.commit()
    k.close()
    vyvod, plohih = '', 0
    for nazv, kat, pr in (('каталог как есть', tk, ''), ('копия каталога с пробными значениями: ' + ','.join(probnye), tk2, ','.join(probnye))):
        r = subprocess.run([VENV, os.path.abspath(__file__), '--render', stage, kat, ts, pr], capture_output=True, timeout=900,
                           cwd=KOREN, env=dict(os.environ, PYTHONIOENCODING='utf-8'))
        v = r.stdout.decode('utf-8', 'replace') + (r.stderr.decode('utf-8', 'replace')[-2500:] if r.returncode else '')
        vyvod += '----- %s: %s\n%s\n' % (metka, nazv, v)
        if r.returncode or 'ПЛОХИХ ПРОВЕРОК: 0' not in v:
            plohih += 1
    io.open(os.path.join(DROP, 'fixK-vid-%s-%s.txt' % (metka, VREMYA)), 'w', encoding='utf-8').write(vyvod)
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


PAPKA = os.path.join(KOREN, '_bekap', 'fixK-vid-' + VREMYA)
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
    vzyat_zamok('fixK (паспорт MEYER-7: centro.html)')
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
        print('ПРИМЕНЕНО: %s; копия прежних файлов: %s (перезапуск не нужен)' % (
            ', '.join(STAGE_PUT[k_] for k_ in izm) or 'ничего', PAPKA))
    finally:
        otdat_zamok()
