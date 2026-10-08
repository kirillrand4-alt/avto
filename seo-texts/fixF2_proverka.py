# -*- coding: utf-8 -*-
"""fixF2: проверка после доводки данных (только чтение боевых баз; всё – на копиях).

    python3 zapusk_na_servere.py fixF2_proverka.py <папка копий «до» в C:\\centro2\\_bekap>

  * «до» – копии баз, снятые fixF2_dannye.py перед записью; «после» – свежие копии боевых баз;
  * рендер TestClient (venv) на каждой паре: список очереди meyer1 (Пяткова) и meyer3, карточки
    примеров (админ) и карточка №1 продавца – HTML в zip на дроп (fixF2-render-<до|после>-<время>.zip);
  * на «после» – проверки данных у всех 600: флаги ЛПР компании = пересчёт по контактам карточки;
    ступень и балл очереди в базе продаж = расчёт формулы E2 (3s_fixF2_ball.py); lpr_kratko
    показывает контакт, по которому дана ступень; номера со «связанного юрлица» не помечены чужими;
  * сравнение топ-20 Пятковой до/после – в выводе и в fixF2-proverka-<время>.txt на дроп.
"""
import html as H
import importlib.util
import io
import json
import os
import re
import sqlite3
import subprocess
import sys
import time
import zipfile

VENV = r'C:\seostat\.venv\Scripts\python.exe'
KOREN = r'C:\centro2'
KAT = os.path.join(KOREN, 'data', 'meyer_baza1.db')
SALES = os.path.join(KOREN, 'data', 'centro_sales_meyer1.db')
DROP = r'C:\seostat\drop\drop-storage'
PUT = '/obzvon-meyer'
BALL = r'C:\sender\_ops\3s_fixF2_ball.py'
PRIMERY = ['3524015320', '2225132970', '9723051780', '3623007585', '9303024328', '4706054164', '7724766868',
           '4401163232', '3525279862', '5252000632', '0259009339', '1829013726']
STUPEN = {4: 800, 3: 600, 2: 400, 1: 200, 0: 0}


def kopiya(src_put, dst_put):
    src = sqlite3.connect('file:%s?mode=ro' % src_put, uri=True)
    dst = sqlite3.connect(dst_put)
    src.backup(dst)
    dst.close()
    src.close()


def clean(s):
    return re.sub(r'\s+', ' ', H.unescape(re.sub(r'<[^>]+>', ' ', s or ''))).strip()


def razbor_spiska(h):
    h = re.sub(r'(?s)<(script|style)[^>]*>.*?</\1>', '', h)
    rows = []
    for tr in re.findall(r'(?s)<tr[^>]*>(.*?)</tr>', h):
        m = re.search(r'centro\?inn=(\d{10,12})', tr)
        if not m:
            continue
        r = {'inn': m.group(1)}
        mm = re.search(r'och-ball"[^>]*>([-\d.]+)</td>', tr)
        r['ball'] = float(mm.group(1)) if mm else None
        mm = re.search(r'och-ball" title="([^"]*)"', tr)
        r['pochemu'] = H.unescape(mm.group(1))[:60] if mm else ''
        mm = re.search(r'(?s)class="nazv"[^>]*>(.*?)</a>', tr)
        r['nazv'] = clean(mm.group(1))[:40] if mm else ''
        mm = re.search(r'(?s)<td class="lpr-yach och-lpr">(.*?)</td>', tr)
        r['lpr'] = clean(mm.group(1))[:110] if mm else ''
        rows.append(r)
    return rows


def razbor_kartochki(h):
    h = re.sub(r'(?s)<(script|style)[^>]*>.*?</\1>', '', h)
    out = []
    cs = re.search(r'(?s)<section class="card contacts-section">(.*?)</section>', h)
    if not cs:
        return out
    cst = cs.group(1)
    fi = cst.find('<details class="fold">')
    for part, gde in ((cst if fi < 0 else cst[:fi], 'верх'), ('' if fi < 0 else cst[fi:], 'остальные')):
        for art in re.findall(r'(?s)<article class="contact-card.*?</article>', part):
            c = {'gde': gde}
            if 'kontakt-sprosit' in art:
                m = re.search(r'(?s)<p class="sprosit-tekst">(.*?)</p>', art)
                c['nomer'] = clean(m.group(1)) if m else ''
            else:
                m = re.search(r'(?s)class="contact-value[^"]*"[^>]*>(.*?)</', art)
                c['nomer'] = clean(m.group(1)) if m else ''
            m = re.search(r'(?s)<div class="contact-person">\s*<b>(.*?)</b>(.*?)</div>', art)
            c['kto'] = (clean(m.group(1)) + ' | ' + clean(m.group(2))) if m else ''
            m = re.search(r'(?s)<span class="uroven-lpr">(.*?)</span>', art)
            c['uroven'] = clean(m.group(1)) if m else ''
            b = re.search(r'(?s)<span class="badges">(.*?)</span>\s*</div>', art)
            c['metki'] = [clean(t) for t in re.findall(r'(?s)<span class="tag[^"]*"[^>]*>(.*?)</span>', b.group(1))] if b else []
            m = re.search(r'(?s)<div class="chuzhoy-metka">(.*?)</div>', art)
            c['chuzhoy'] = clean(m.group(1)) if m else ''
            m = re.search(r'(?s)<details class="vid-pochemu"><summary>(.*?)</summary><p>(.*?)</p>', art)
            c['pochemu'] = (clean(m.group(1)) + ': ' + clean(m.group(2)))[:160] if m else ''
            m = re.search(r'(?s)<div class="source-line"[^>]*>(.*?)</div>', art)
            c['istochnik'] = clean(m.group(1))[:90] if m else ''
            out.append(c)
    return out


# ====================================================================== РЕНДЕР (venv, копии баз)
if '--render' in sys.argv:
    i = sys.argv.index('--render')
    metka, tkat, tsales, vyhod = sys.argv[i + 1:i + 5]
    proverki = '--proverki' in sys.argv
    import warnings
    warnings.filterwarnings('ignore')
    sys.path.insert(0, KOREN)
    import zapusk  # noqa: F401
    import logging
    logging.disable(logging.CRITICAL)
    for kk in ('CENTRO_SALES_DB', 'PARK_OCHERED_SALES_DB'):
        os.environ[kk] = tsales
    for kk in ('CENTRIFUGAL_DB', 'CENTRO_DB', 'PARK_OCHERED_DB'):
        os.environ[kk] = tkat
    from app.api import routes_centro_sales as rcs
    from app.services import centro_catalog as catalog
    from app.services import centro_sales as sales
    from app.obzvon import create_app
    from fastapi.testclient import TestClient
    assert str(catalog.db_path()) == tkat and str(sales.sales_db_path()) == tsales, 'не копии баз'
    vnutr = next(z for z in vars(create_app()).values() if hasattr(z, 'routes') and hasattr(z, 'dependency_overrides'))
    ADMIN = {'id': 0, 'username': 'meyer_admin', 'role': 'admin', 'is_active': 1}
    kto = {'u': ADMIN}
    vnutr.dependency_overrides[rcs.current_user] = lambda: kto['u']
    rez = {'metka': metka, 'kody': {}, 'spiski': {}, 'kartochki': {}}
    with TestClient(vnutr) as kl, zipfile.ZipFile(vyhod, 'w', zipfile.ZIP_DEFLATED) as z:
        def poluchit(imya, u, kak, **kw):
            kto['u'] = kak
            o = kl.get(PUT + u, **kw)
            rez['kody'][imya] = o.status_code
            z.writestr(imya + '.html', o.text)
            return o
        for n_p, p in ((1, 'meyer1'), (3, 'meyer3')):
            PROD = {'id': n_p, 'username': p, 'role': 'sales', 'is_active': 1}
            o = poluchit('spisok_' + p, '/centro', PROD, params={'size': 100, 'page': 1})
            rez['spiski'][p] = razbor_spiska(o.text)[:25]
            if rez['spiski'][p]:
                poluchit('prodavec_%s_kartochka1' % p, '/centro', PROD, params={'inn': rez['spiski'][p][0]['inn']})
        for inn in PRIMERY:
            o = poluchit('card_' + inn, '/centro', ADMIN, params={'inn': inn})
            rez['kartochki'][inn] = razbor_kartochki(o.text)
        poluchit('admin_glavnaya', '/centro', ADMIN)
        poluchit('admin_stats', '/centro/stats', ADMIN)
    if proverki:
        spec = importlib.util.spec_from_file_location('fixF2_ball', BALL)
        E = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(E)
        k = sqlite3.connect('file:%s?mode=ro' % tkat, uri=True)
        k.row_factory = sqlite3.Row
        s = sqlite3.connect('file:%s?mode=ro' % tsales, uri=True)
        s.row_factory = sqlite3.Row
        naz = {r['inn']: dict(r) for r in s.execute('SELECT * FROM company_assignment')}
        komp = {r['inn']: dict(r) for r in k.execute('SELECT * FROM company')}

        def pokaz(v):
            osn, dob = catalog._razdelit_dobavochnyy(v)
            d = re.sub(r'\D', '', osn)
            if len(d) == 11 and d[0] == '7':
                osn = '+7 %s %s-%s-%s' % (d[1:4], d[4:7], d[7:9], d[9:])
            return osn + (' доб. ' + dob if dob else '')
        ne_flagi, ne_stupen, ne_ball, ne_kratko, chuzh_svyaz = [], [], [], [], []
        POLYA = ('has_tech', 'n_tech', 'has_purchaser', 'n_purchaser', 'lpr_mobilnyy', 'lpr_s_fio', 'lpr_roli', 'n_phones', 'has_phone')
        for inn, c in komp.items():
            items = catalog.contacts(inn)
            tel = [x for x in items if x['kind'] == 'phone']
            lpr = [x for x in tel if x['lpr']]
            mob = [x for x in lpr if x['vid_nomera'] == 'мобильный']
            novoe = {'has_tech': int(any(x['is_tech'] for x in lpr)), 'n_tech': sum(1 for x in lpr if x['is_tech']),
                     'has_purchaser': int(any(x['is_purchaser'] for x in lpr)),
                     'n_purchaser': sum(1 for x in lpr if x['is_purchaser']), 'lpr_mobilnyy': int(bool(mob)),
                     'lpr_s_fio': len({catalog._kl_fio(x['person']) for x in lpr if x['person']}),
                     'lpr_roli': ', '.join(dict.fromkeys(x['rol_vid'] for x in lpr)), 'n_phones': len(tel),
                     'has_phone': int(bool(tel))}
            raz = [p for p in POLYA if c.get(p) != novoe[p]]
            if raz:
                ne_flagi.append((inn, raz))
            d = E.razbor_kompanii(c, items, catalog, sales)
            a = naz.get(inn)
            if a:
                if a.get('stupen_ocheredi') != d['tier']:
                    ne_stupen.append((inn, a.get('stupen_ocheredi'), d['tier']))
                if abs(float(a['assignment_score']) - d['score']) > 0.06:
                    ne_ball.append((inn, a['assignment_score'], d['score']))
                if not (STUPEN[d['tier']] <= float(a['assignment_score']) < STUPEN[d['tier']] + 200) and d['tier']:
                    ne_ball.append((inn, 'вне диапазона ступени', a['assignment_score'], d['tier']))
            kr = str(c.get('lpr_kratko') or '')
            t = d['t_lpr']
            if lpr:
                fio_mob = [x for x in mob if x['person']]
                nuzhnye = fio_mob if t == 4 else mob if t == 3 else lpr
                if not any(pokaz(x['value']) in kr for x in nuzhnye):
                    ne_kratko.append((inn, t, kr[:90]))
            elif not (kr.startswith('ЛПР не найден') or 'спросить у приёмной' in kr):
                ne_kratko.append((inn, t, kr[:90]))
            for x in tel:
                if str(x.get('svyaz_adres') or '').strip() and (x.get('chuzhoy_istochnik') or x['rol_vid'] == 'с сайта другого юрлица'):
                    chuzh_svyaz.append((inn, x['id']))
        rez['proverki'] = {
            'kompaniy': len(komp), 'naznacheniy': len(naz),
            'flagi_ne_sovpali': ne_flagi[:20], 'flagi_ne_sovpali_n': len(ne_flagi),
            'stupen_ne_sovpala': ne_stupen[:20], 'stupen_ne_sovpala_n': len(ne_stupen),
            'ball_ne_sovpal': ne_ball[:20], 'ball_ne_sovpal_n': len(ne_ball),
            'lpr_kratko_ne_po_stupeni': ne_kratko[:20], 'lpr_kratko_ne_po_stupeni_n': len(ne_kratko),
            'svyaz_no_chuzhoy': chuzh_svyaz,
            'po_stupenyam': {p: dict(sorted(__import__('collections').Counter(
                naz[i].get('stupen_ocheredi') for i in naz if naz[i]['username'] == p).items(), key=lambda x: str(x[0])))
                for p in ('meyer1', 'meyer2', 'meyer3', 'meyer4')},
        }
    print(json.dumps(rez, ensure_ascii=False))
    raise SystemExit(0)

# ====================================================================== ГЛАВНОЕ (системный питон)
DO = sys.argv[1]
VREMYA = time.strftime('%Y%m%d-%H%M%S')
papka = os.path.join(KOREN, '_bekap', 'fixF2-proverka-' + VREMYA)
os.makedirs(papka, exist_ok=True)
pary = {'do': (os.path.join(papka, 'do_kat.db'), os.path.join(papka, 'do_sales.db')),
        'posle': (os.path.join(papka, 'posle_kat.db'), os.path.join(papka, 'posle_sales.db'))}
kopiya(os.path.join(DO, 'meyer_baza1.db'), pary['do'][0])
kopiya(os.path.join(DO, 'centro_sales_meyer1.db'), pary['do'][1])
kopiya(KAT, pary['posle'][0])
kopiya(SALES, pary['posle'][1])
rez = {}
for metka, (tk, ts) in pary.items():
    zp = os.path.join(DROP, 'fixF2-render-%s-%s.zip' % (metka, VREMYA))
    r = subprocess.run([VENV, os.path.abspath(__file__), '--render', metka, tk, ts, zp] + (['--proverki'] if metka == 'posle' else []),
                       capture_output=True, timeout=1200, cwd=KOREN, env=dict(os.environ, PYTHONIOENCODING='utf-8'))
    vyv = r.stdout.decode('utf-8', 'replace').strip().splitlines()
    try:
        rez[metka] = json.loads(vyv[-1])
    except (ValueError, IndexError):
        print('РЕНДЕР %s НЕ УДАЛСЯ: %s' % (metka, r.stderr.decode('utf-8', 'replace')[-2500:]))
        raise SystemExit(1)
stroki = []
for metka in ('do', 'posle'):
    stroki.append('коды %s: %s' % (metka, rez[metka]['kody']))
for p in ('meyer1', 'meyer3'):
    stroki.append('\n=== очередь %s, топ-20: ДО -> ПОСЛЕ' % p)
    a, b = rez['do']['spiski'][p][:20], rez['posle']['spiski'][p][:20]
    for n in range(20):
        x = a[n] if n < len(a) else {}
        y = b[n] if n < len(b) else {}
        stroki.append('%2d. %s %-28s %7s | %s %-28s %7s  %s' % (n + 1, x.get('inn', ''), x.get('nazv', '')[:28], x.get('ball', ''),
                                                              y.get('inn', ''), y.get('nazv', '')[:28], y.get('ball', ''),
                                                              y.get('lpr', '')[:70]))
    gde = {r['inn']: n + 1 for n, r in enumerate(rez['posle']['spiski'][p])}
    for r in rez['do']['spiski'][p][:20]:
        if r['inn'] in ('3524015320', '2225132970', '9723051780', '3623007585', '9303024328'):
            stroki.append('   %s: было место %s (%s), стало %s' % (r['inn'], rez['do']['spiski'][p].index(r) + 1, r['ball'],
                                                                   gde.get(r['inn'], '> 25')))
for inn in PRIMERY:
    stroki.append('\n=== карточка %s' % inn)
    for metka in ('do', 'posle'):
        stroki.append('  [%s]' % metka)
        for c in rez[metka]['kartochki'].get(inn, [])[:12]:
            stroki.append('    %-9s %-30s %-50s %s %s %s' % (c['gde'], c['nomer'][:30], c['kto'][:50], ('ЛПР: ' + c['uroven']) if c['uroven'] else '',
                                                        ','.join(c['metki'])[:60], ('ЧУЖОЙ: ' + c['chuzhoy'][:60]) if c['chuzhoy'] else ''))
            if metka == 'posle' and c['pochemu']:
                stroki.append('              почему: %s' % c['pochemu'][:150])
stroki.append('\n=== проверки данных (после): %s' % json.dumps(rez['posle'].get('proverki'), ensure_ascii=False))
tekst = '\n'.join(stroki)
io.open(os.path.join(DROP, 'fixF2-proverka-%s.txt' % VREMYA), 'w', encoding='utf-8').write(tekst)
io.open(os.path.join(DROP, 'fixF2-proverka-%s.json' % VREMYA), 'w', encoding='utf-8').write(json.dumps(rez, ensure_ascii=False))
for t in list(pary.values()):
    for f in t:
        try:
            os.remove(f)
        except OSError:
            pass
print(tekst[-5800:])
print('\nполный текст: fixF2-proverka-%s.txt / .json; HTML: fixF2-render-{do,posle}-%s.zip' % (VREMYA, VREMYA))
