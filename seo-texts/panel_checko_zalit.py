# -*- coding: utf-8 -*-
r"""Реквизиты, руководитель, финансы и контакты из checko.ru в карточки панели Meyer
(владелец 08.10: «заполни эти поля информацией из чеко»: адрес, директор, статус ЕГРЮЛ, почта,
чистая прибыль, сотрудники).

Вход – разбор страниц checko (panel_checko_razbor.py) на дропе: checko-meyer-razbor.json.
Что пишется (только где checko отдал значение и ИНН страницы = ИНН компании):
  adres, direktor («ФИО (должность, с дд.мм.гггг)»), status_egrul;
  ssch + ssch_god; chistaya_pribyl + fin_god и выручка ЗА ТОТ ЖЕ год (в карточке год стоит
  у обеих строк; прежняя выручка, если отличалась, сохраняется в vyruchka_ishodnaya);
  почта: пустое поле «Почта» – почтами checko, иначе они идут в «Почты (чеко)» (кроме уже
  показанных); пустой «Сайт» – сайтом из checko. Телефоны checko НЕ пишутся никуда (владелец
  08.10: «телефоны из чеко бесполезны, не добавляй их»).
Источник: istochnik_rekvizitov дописывается, в «Источники проверки компании» – ссылка на
страницу checko. Порядок продавцов, назначения, статусы и приоритеты не меняются.
Перед записью – копия каталога (sqlite backup); проверка через TestClient; провал –
каталог возвращается из копии.
"""
import io
import json
import os
import re
import sqlite3
import subprocess
import sys
import time

VENV = r'C:\seostat\.venv\Scripts\python.exe'
KOREN = r'C:\centro2'
KAT = os.path.join(KOREN, 'data', 'meyer_baza1.db')
DROP = r'C:\seostat\drop\drop-storage'
RAZBOR = os.path.join(DROP, 'checko-meyer-razbor.json')
PUT = '/obzvon-meyer'
DATA = time.strftime('%d.%m.%Y')
METKA = 'checko.ru %s' % DATA
POLE_ISTOCHNIKA = 'Реквизиты, руководитель, финансы, контакты (checko)'


def direktor(z):
    fio = (z.get('ruk_fio') or '').strip()
    if not fio:
        return ''
    dolzh = (z.get('ruk_dolzhnost') or '').strip()
    if dolzh and not dolzh.isupper():
        dolzh = dolzh[0].lower() + dolzh[1:]
    hv = ', '.join(x for x in (dolzh, ('с ' + z['ruk_s']) if z.get('ruk_s') else '') if x)
    return '%s (%s)' % (fio, hv) if hv else fio


def spisok(pary, uzhe=()):
    out = []
    for znach, prim in pary:
        if znach.lower() in uzhe:
            continue
        out.append('%s (%s)' % (znach, prim) if prim else znach)
    return ', '.join(out)


def plan(k, d):
    """Список изменений по компаниям: [(inn, {kolonka: novoe}), ...] и счётчики."""
    sch = {}
    izm = []
    for r in k.execute('select * from company'):
        c = dict(r)
        z = d.get(c['inn'])
        if not z:
            sch['нет страницы checko'] = sch.get('нет страницы checko', 0) + 1
            continue
        if z.get('oshibka'):
            sch['страница не карточка компании'] = sch.get('страница не карточка компании', 0) + 1
            continue
        n = {}
        if z.get('adres'):
            n['adres'] = z['adres']
        if direktor(z):
            n['direktor'] = direktor(z)
        if z.get('status'):
            n['status_egrul'] = z['status'] + (('; правопреемник %s' % z['pravopreemnik']) if z.get('pravopreemnik') else '')
        if z.get('ssch') is not None:
            n['ssch'] = z['ssch']
            n['ssch_god'] = z.get('ssch_god') or ''
        if z.get('fin_god') and (z.get('pribyl') is not None or z.get('vyruchka') is not None):
            n['fin_god'] = z['fin_god']
            n['chistaya_pribyl'] = z.get('pribyl')
            if z.get('vyruchka') is not None:
                staraya = c.get('vyruchka_rub')
                try:
                    staraya_f = float(staraya) if staraya not in (None, '') else None
                except ValueError:
                    staraya_f = None
                if staraya_f is not None and abs(staraya_f - float(z['vyruchka'])) > max(1.0, 0.005 * abs(staraya_f)):
                    n['vyruchka_ishodnaya'] = staraya
                    sch['выручка обновлена (отличалась)'] = sch.get('выручка обновлена (отличалась)', 0) + 1
                elif staraya_f is None:
                    sch['выручка была пустой'] = sch.get('выручка была пустой', 0) + 1
                n['vyruchka_rub'] = z['vyruchka']
        poch = [[e, p] for e, p in (z.get('pochty') or [])]
        if poch:
            if not (c.get('pochta') or '').strip():
                n['pochta'] = spisok(poch)
            else:
                uzhe = set(x.strip().lower() for x in re.split(r'[,;\s]+', c['pochta']) if '@' in x)
                dop = spisok(poch, uzhe)
                if dop:
                    n['pochty_checko'] = dop
        # телефоны checko НЕ пишутся: владелец 08.10 «телефоны из чеко бесполезны, не добавляй их»
        if z.get('sayty') and not (c.get('sayt') or '').strip():
            n['sayt'] = z['sayty'][0]
        ist = (c.get('istochnik_rekvizitov') or '').strip()
        if 'checko.ru' not in ist or METKA not in ist:
            n['istochnik_rekvizitov'] = (ist + ' | ' if ist else '') + METKA
        n = {kk: v for kk, v in n.items() if c.get(kk) != v}
        for kk in n:
            sch['поле ' + kk] = sch.get('поле ' + kk, 0) + 1
        if z.get('status') and 'Действующ' not in z['status']:
            sch.setdefault('_не_действующие', []).append([c['inn'], c.get('predpriyatie'), n.get('status_egrul') or z['status']])
        izm.append((c['inn'], n, z.get('ogrn') or ''))
    return izm, sch


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
    d = json.load(io.open(RAZBOR, encoding='utf-8'))
    k = sqlite3.connect('file:%s?mode=ro' % KAT, uri=True)
    k.row_factory = sqlite3.Row
    plohih = 0

    def proverit(u, t):
        global plohih
        if not u:
            plohih += 1
        print('   %s %s' % ('ОК ' if u else 'ПЛОХО', t))

    vse = [dict(r) for r in k.execute('select * from company')]
    pusto = {p: sum(1 for c in vse if c.get(p) in (None, '')) for p in
             ('adres', 'direktor', 'status_egrul', 'pochta', 'chistaya_pribyl', 'ssch', 'fin_god', 'vyruchka_rub', 'sayt')}
    print('   пустых полей после заливки (из %d): %s' % (len(vse), pusto))
    vnutr = next(z for z in vars(create_app()).values() if hasattr(z, 'routes') and hasattr(z, 'dependency_overrides'))
    vnutr.dependency_overrides[rcs.current_user] = lambda: {'id': 0, 'username': 'meyer_admin', 'role': 'admin', 'is_active': 1}
    def chislo(x):
        try:
            return float(x)
        except (TypeError, ValueError):
            return 0.0
    primery = ['3227005513'] + [c['inn'] for c in vse if chislo(c.get('chistaya_pribyl')) < 0][:1] + \
              [c['inn'] for c in vse if c.get('pochty_checko')][:1] + [c['inn'] for c in vse if c['inn'] in d][::150]
    with TestClient(vnutr) as kl:
        for inn in dict.fromkeys(primery):
            c = next((x for x in vse if x['inn'] == inn), None)
            if not c:
                continue
            o = kl.get(PUT + '/centro?inn=' + inn)
            t = o.text
            i = t.find('Реквизиты и руководство')
            j = t.find('Все ОКВЭД', i) if i > 0 else -1
            blok = t[i:j if j > i else i + 6000]
            dd = dict(re.findall(r'<dt>([^<]+)</dt><dd>(.*?)</dd>', blok, re.S))
            dd = {kk: re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', '', v)).strip() for kk, v in dd.items()}
            ok = o.status_code == 200 and all(dd.get(p, '–') != '–' for p, kol in
                                              (('Адрес', 'adres'), ('Директор', 'direktor'), ('Статус ЕГРЮЛ', 'status_egrul'),
                                               ('Чистая прибыль', 'chistaya_pribyl'), ('Сотрудники', 'ssch'))
                                              if c.get(kol) not in (None, ''))
            proverit(ok, 'карточка %s %s: %s' % (inn, o.status_code, {kk: v[:70] for kk, v in dd.items()
                                                                    if kk in ('Адрес', 'Директор', 'Статус ЕГРЮЛ', 'Почта', 'Выручка',
                                                                              'Чистая прибыль', 'Сотрудники', 'Почты (чеко)')}))
            if inn == '3227005513':
                io.open(os.path.join(DROP, 'centro2-checko-karta-%s.html' % inn), 'w', encoding='utf-8').write(t)
        st = kl.get(PUT + '/centro')
        proverit(st.status_code == 200 and re.search(r'<b class="total-count">\d+ компаний</b>', st.text), 'главная: %s' % st.status_code)
        st = kl.get(PUT + '/centro/stats')
        proverit(st.status_code == 200, 'статистика: %s' % st.status_code)
    print('ПЛОХИХ ПРОВЕРОК: %d' % plohih)
    raise SystemExit(1 if plohih else 0)

# ====================================================================== ОСНОВНОЙ ХОД
SUHOY = '--suhoy' in sys.argv
d = json.load(io.open(RAZBOR, encoding='utf-8'))
k = sqlite3.connect(KAT)
k.row_factory = sqlite3.Row
izm, sch = plan(k, d)
nd = sch.pop('_не_действующие', [])
print('компаний с изменениями: %d' % sum(1 for _, n, _ in izm if n))
print(json.dumps(sch, ensure_ascii=False, indent=0))
print('не действующие по checko: %s' % nd)
print('уже было «Телефоны (чеко)» из прежних заливок (не трогаю): %d' %
      k.execute("select count(*) from company where coalesce(telefony_checko,'')<>''").fetchone()[0])
if SUHOY:
    raise SystemExit(0)
B = os.path.join(KOREN, '_bekap', time.strftime('checko-%Y%m%d-%H%M%S'))
os.makedirs(B, exist_ok=True)
kopiya = sqlite3.connect(os.path.join(B, 'meyer_baza1.db'))
k.backup(kopiya)
kopiya.close()
print('копия каталога:', B)
kol = [r[1] for r in k.execute('pragma table_info(company)')]
try:
    with k:
        if 'vyruchka_ishodnaya' not in kol:
            k.execute('ALTER TABLE company ADD COLUMN vyruchka_ishodnaya TEXT')
        for inn, n, ogrn in izm:
            if n:
                k.execute('UPDATE company SET %s WHERE inn=?' % ', '.join('%s=?' % kk for kk in n), list(n.values()) + [inn])
            if ogrn and not k.execute('select 1 from company_source where inn=? and field_name=?', (inn, POLE_ISTOCHNIKA)).fetchone():
                k.execute('INSERT INTO company_source (inn, field_name, source, source_url) VALUES (?,?,?,?)',
                          (inn, POLE_ISTOCHNIKA, METKA, 'https://checko.ru/company/' + ogrn))
except Exception as e:  # noqa: BLE001
    print('ЗАПИСЬ НЕ УДАЛАСЬ, откат транзакции:', repr(e)[:300])
    raise SystemExit(1)
k.close()
print('записано')
r = subprocess.run([VENV, os.path.abspath(__file__), '--proverka'], capture_output=True, timeout=900, cwd=KOREN,
                   env=dict(os.environ, PYTHONIOENCODING='utf-8'))
sys.stdout.write(r.stdout.decode('utf-8', 'replace'))
if r.returncode:
    sys.stdout.write(r.stderr.decode('utf-8', 'replace')[-2500:])
    iz = sqlite3.connect(os.path.join(B, 'meyer_baza1.db'))
    v = sqlite3.connect(KAT)
    iz.backup(v)  # возврат тем же backup API: панель держит каталог открытым
    v.close()
    iz.close()
    print('ПРОВЕРКА НЕ ПРОШЛА – каталог возвращён из копии')
    raise SystemExit(1)
print('ГОТОВО')
