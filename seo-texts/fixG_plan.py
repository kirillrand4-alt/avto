# -*- coding: utf-8 -*-
"""fixG (локально): отбор 13 замен и план заливки (владелец 09.10: «выкинь их, добавь из последнего
списка нормальных компаний»).

ОТБОР – кандидаты файла 3 по рейтингу скрипта Базы 3 (fixG_kandidaty.py), по порядку, пока не 13:
  1. страница checko найдена, ИНН совпал; статус «Действующая»;
  2. выручка по checko 100–1000 млн (как у Базы 3);
  3. основной ОКВЭД (checko; совпал с файлом) даёт сегмент по okved_segment_tz.json;
  4. сайт ДОКАЗАННО свой – разбор агента D (fixD_chey_sayt.py): на сайте ИНН или ОГРН компании,
     либо руководитель или юрадрес из checko; только название (+ город) – недостаточно;
     плюс ручные отказы с причиной (сайт другого юрлица группы, карточка на платформе);
  5. настоящий мобильный (флаг скрипта Базы 3) сейчас стоит на странице своего домена.
ПЛАН – строки каталога для 13 (как у загрузчика Базы 3) + доводка до уровня остальных:
  реквизиты и деньги checko (как panel_checko_zalit.plan; телефоны checko не берутся),
  регион/пояс/сегмент/попадание/пометка (fixE1_regiony_segmenty.plan с таблицей
  okved_segment_tz.json, в т. ч. 46.21), отрасль (panel_segmenty_regiony.otrasl), «чей сайт» (D),
  подписи и роли номеров (разбор C + решения по странице из fixG-ruchnye.json – в репо номеров нет),
  ЛПР без телефона («спросить у приёмной»), холдинг. Раздача продавцам – перебором всех вариантов
  (каждому столько, сколько он теряет; холдинг – к продавцу группы) по показателям отчёта E2.

    python3 fixG_plan.py <рабочая папка fixG> <выход plan.json>
"""
import collections
import copy
import gzip
import io
import itertools
import json
import math
import os
import re
import shutil
import sqlite3
import sys
import time

W, OUT = sys.argv[1:3]
ZDES = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ZDES)
DATA = time.strftime('%d.%m.%Y')
SIM = os.path.join(W, 'sim')
os.makedirs(SIM, exist_ok=True)
for f in ('meyer_baza1.db', 'centro_sales_meyer1.db'):
    shutil.copy(os.path.join(W, 'db0', f), os.path.join(SIM, f))
os.environ['CENTRIFUGAL_DB'] = os.environ['CENTRO_DB'] = os.path.join(SIM, 'meyer_baza1.db')
os.environ['CENTRO_SALES_DB'] = os.path.join(SIM, 'centro_sales_meyer1.db')
sys.path.insert(0, os.path.join(W, 'kodroot'))
from app.services import centro_catalog as cat  # noqa: E402
from app.services import centro_sales as sales  # noqa: E402
import fixC_razbor as R  # noqa: E402
import fixE1_regiony_segmenty as E1  # noqa: E402
import fixF2_ball as E2  # noqa: E402

TZ = json.load(open(os.path.join(ZDES, 'okved_segment_tz.json'), encoding='utf-8'))
E1.OKVED_TZ.update(TZ)          # копия таблицы в E1 – до 46.21; берётся текущая таблица
OTRASLI = [('10.11', 'мясо и птица'), ('10.12', 'мясо и птица'), ('10.13', 'мясо и птица'),
           ('10.2', 'рыба и морепродукты'), ('10.3', 'овощи, фрукты, ягоды, орехи'), ('10.4', 'масла и жиры'),
           ('10.51.4', 'сыры'), ('10.5', 'молоко и мороженое'), ('10.61', 'мука, крупы, зерно'), ('10.62', 'крахмал'),
           ('10.71', 'хлеб и выпечка'), ('10.72', 'печенье, сухари, мучные кондитерские'), ('10.73', 'макароны'),
           ('10.81', 'сахар'), ('10.82', 'кондитерские изделия'), ('10.83', 'чай и кофе'),
           ('10.84', 'специи, соусы, соль'), ('10.85', 'готовая еда'), ('10.86', 'детское и диетическое питание'),
           ('10.89', 'прочие пищевые продукты'), ('10.9', 'корма'), ('11', 'напитки'),
           ('52.10', 'зерно, семена, элеваторы'), ('46.21', 'зерно, семена, элеваторы'), ('01.1', 'зерно, семена, элеваторы'),
           ('01.6', 'зерно, семена, элеваторы'), ('01.2', 'сады, ягоды, орехи'), ('01.4', 'животноводство'),
           ('01', 'сельское хозяйство'), ('46.3', 'оптовая торговля продуктами'), ('46', 'оптовая торговля'),
           ('47', 'розничная торговля')]


def otrasl(kod):        # = panel_segmenty_regiony.otrasl
    kod = (kod or '').strip()
    l = max((n for n, _ in OTRASLI if kod.startswith(n)), key=len, default='')
    return dict(OTRASLI)[l] if l else 'прочее'


def zagr(p):
    return json.load(open(os.path.join(W, p), encoding='utf-8'))


kand = zagr('kand/kandidaty.json')
b3 = zagr('kand/meyer-fixG-kand.json')
razbor = zagr('checko/razbor.json')
svyazi = zagr('checko/svyazi.json')
chey = zagr('chey.json')
chey.update(zagr('v2/chey.json'))
ruchnye = zagr('fixG-ruchnye.json')
indeks = zagr('pages/_indeks.json')

# ручные отказы (проверено по страницам 09.10)
RUCHNO_OTKAZ = {
    '5906148485': 'сайт naturalsupp.ru – другого юрлица группы: в реквизитах сайта ООО «НАТУРАЛЬНЫЕ ДОБАВКИ» '
                  'ИНН 5904384046 (производитель); руководитель ТД на сайте только контакт в вакансиях – сайт не свой',
    '2503029472': 'сайт – карточка на платформе farmer112.ru (LEGOS «Ярмарка»), не собственный сайт; юрадрес на '
                  'ней – из ЕГРЮЛ и принадлежность номера не доказывает (правило Базы 3: не мини-сайт справочника)',
}


def domen(u):
    u = (u or '').strip().lower()
    if '//' in u:
        u = u.split('//', 1)[1]
    d = u.split('/', 1)[0].split('?', 1)[0].split(':', 1)[0].strip('.')
    return d[4:] if d.startswith('www.') else d


_kesh = {}


def stranica(url):
    if url not in _kesh:
        z = indeks.get(url) or {}
        res = None
        if z.get('fajl') and z.get('kod') == 200:
            t, _ = R.html_v_tekst(R.dekodirovat(gzip.open(os.path.join(W, 'pages', z['fajl'])).read(), z.get('tip', '')))
            res = {'t': t, 'vh': R.nomera_v_tekste(t)}
        _kesh[url] = res
    return _kesh[url]


def k10(v):
    osn, dob = cat._razdelit_dobavochnyy(v)
    return R.klyuch10(R.cifry(osn)), dob


def mobilnyy_na_stranice(c, sd):
    """Настоящий мобильный (флаг Базы 3) сейчас стоит на странице своего домена."""
    stranicy = [u for u, z in indeks.items() if domen(u) == sd and z.get('kod') == 200]
    for n in c['nomera']:
        if not n['nastoyashchiy'] or domen(n['url']) != sd:
            continue
        kk = k10(n['nomer'])[0]
        for u in [n['url']] + stranicy:
            st = stranica(u)
            if st and any(x['k10'] == kk for x in st['vh']):
                return True, n['nomer'], u
    return False, '', ''


def proverka_sayta(inn):
    x = chey.get(inn)
    if not x:
        return False, 'сайт не проверялся', [], ''
    sd = x['sayt_domen']
    v = x['domeny'].get(sd) or {}
    tverd = [s for s in v.get('svoj', []) if s.startswith(('ИНН', 'ОГРН', 'руководитель', 'юрадрес'))]
    if inn in RUCHNO_OTKAZ:
        return False, RUCHNO_OTKAZ[inn], tverd, sd
    if tverd:
        return True, '', v['svoj'], sd
    vd = v.get('verdikt', 'нет сайта')
    if vd == 'свой':
        prich = 'на сайте только название и город/регион (%s) – недостаточно: нет ИНН/ОГРН, руководителя и юрадреса из checko' % '; '.join(v['svoj'])
    elif vd == 'группа':
        prich = 'сайт группы (%s), своего ИНН/ОГРН, руководителя и юрадреса нет' % '; '.join(v['gruppa'])
    elif vd == 'чужой':
        prich = 'сайт другого юрлица: %s' % '; '.join(v['chuzhoy'])
    else:
        prich = 'на сайте нет ИНН/ОГРН, руководителя и юрадреса из checko (страниц скачано %d)' % v.get('stranic', 0)
    return False, prich, v.get('svoj', []), sd


# ====================================================================== 1. ОТБОР
otobrano, otkaz, zapas = [], [], []
for c in kand:
    inn = c['inn']
    z = razbor.get(inn) or {}
    prich = []
    if not z:
        if len(otobrano) >= 13:
            break
        prich.append('страница checko не скачивалась')
    elif z.get('oshibka'):
        prich.append('checko: ' + z['oshibka'])
    else:
        if 'Действующ' not in (z.get('status') or ''):
            prich.append('статус по checko: %s' % z.get('status'))
        v = z.get('vyruchka')
        if v is None or not (1e8 <= float(v) <= 1e9):
            prich.append('выручка по checko %s млн за %s – вне 100–1000' % (round(v / 1e6) if v else '?', z.get('fin_god')))
        okv = ((svyazi.get(inn) or {}).get('okved_osn') or [c['okved']])[0]
        if not E1.po_kodu(okv, TZ):
            prich.append('основной ОКВЭД %s не даёт сегмента по таблице' % okv)
        if okv != c['okved']:
            prich.append('основной ОКВЭД по checko %s ≠ в файле %s' % (okv, c['okved']))
    ok, pr, dok, sd = proverka_sayta(inn)
    if not ok:
        prich.append(pr)
    mob = mobilnyy_na_stranice(c, sd) if ok else (False, '', '')
    if ok and not mob[0]:
        prich.append('настоящего мобильного сейчас нет на странице своего сайта')
    zap = {'mesto': c['mesto'], 'reyting': c['reyting'], 'inn': inn, 'nazvanie': c['nazvanie'], 'okved': c['okved'],
           'vyruchka_checko': z.get('vyruchka'), 'status': z.get('status'), 'sayt': sd, 'dokaz': dok, 'prichiny': prich}
    if len(otobrano) < 13:
        (otkaz if prich else otobrano).append(zap)
    else:
        zap['zapas'] = not prich
        zapas.append(zap)
print('отобрано %d (места %s); отбраковано до 13-го: %d; проверено про запас: %d (годных %d)' % (
    len(otobrano), [x['mesto'] for x in otobrano], len(otkaz), len(zapas), sum(1 for x in zapas if x['zapas'])))
assert len(otobrano) == 13, 'не набралось 13'
SEL = [x['inn'] for x in otobrano]

# ====================================================================== 2. СТРОКИ КАТАЛОГА
b3k = {c['inn']: c for c in b3['kompanii']}
b3n = collections.defaultdict(list)
for x in b3['kontakty']:
    b3n[x['inn']].append(x)
kpo = {c['inn']: c for c in kand}


def direktor(z):        # = panel_checko_zalit.direktor
    fio = (z.get('ruk_fio') or '').strip()
    if not fio:
        return ''
    dolzh = (z.get('ruk_dolzhnost') or '').strip()
    if dolzh and not dolzh.isupper():
        dolzh = dolzh[0].lower() + dolzh[1:]
    hv = ', '.join(x for x in (dolzh, ('с ' + z['ruk_s']) if z.get('ruk_s') else '') if x)
    return '%s (%s)' % (fio, hv) if hv else fio


def spisok(pary, uzhe=()):
    return ', '.join(('%s (%s)' % (e, p) if p else e) for e, p in pary if e.lower() not in uzhe)


E1_KOL = ('region_ishodnyy', 'region_istochnik', 'chas_poyas', 'chas_poyas_kak', 'segment_ishodnyy', 'segment_osn_ishodnyy',
          'segment_dop', 'popadanie_ishodnoe', 'pometka_ocheredi', 'bitrix_klient_sc', 'bitrix_sdelok', 'bitrix_kc_info', 'bitrix_kc')
kompanii, kontakty, lyudi, istochniki, zhurnal_plana = [], [], [], [], []
holding = None
for inn in SEL:
    c = dict(b3k[inn])
    z = razbor[inn]
    ru = ruchnye.get(inn, {})
    row = {kk: v for kk, v in c.items() if kk not in ('sliyanie', 'bitrix_fajl')}
    row['bazy'], row['bazy_opisanie'] = b3['baza'], b3['baza_opisanie']
    # --- checko (как panel_checko_zalit.plan)
    row['adres'] = z.get('adres') or ''
    row['direktor'] = direktor(z)
    row['status_egrul'] = (z.get('status') or '') + (('; правопреемник %s' % z['pravopreemnik']) if z.get('pravopreemnik') else '')
    if z.get('ssch') is not None:
        row['ssch'], row['ssch_god'] = z['ssch'], z.get('ssch_god') or ''
    if z.get('fin_god'):
        row['fin_god'] = z['fin_god']
        row['chistaya_pribyl'] = z.get('pribyl')
        if z.get('vyruchka') is not None:
            st = c.get('vyruchka_rub')
            if st is not None and abs(float(st) - float(z['vyruchka'])) > max(1.0, 0.005 * abs(float(st))):
                row['vyruchka_ishodnaya'] = st
            row['vyruchka_rub'] = z['vyruchka']
    if z.get('pochty'):
        row['pochta'] = spisok(z['pochty'])
    if z.get('sayty') and not (row.get('sayt') or '').strip():
        row['sayt'] = z['sayty'][0]
    row['istochnik_rekvizitov'] = 'checko.ru %s' % DATA
    if z.get('ogrn'):
        istochniki.append({'inn': inn, 'field_name': 'Реквизиты, руководитель, финансы, контакты (checko)',
                           'source': 'checko.ru %s' % DATA, 'source_url': 'https://checko.ru/company/' + z['ogrn']})
    # --- регион, пояс, сегмент, попадание, пометка (E1)
    for kk in E1_KOL:
        row.setdefault(kk, None)
    row['bitrix_kc'] = 0            # Битрикс КЦ – по справочнику на сервере (bitrix_kc_inn.json), при заливке
    row.update({'has_purchaser': int(c['n_purchaser'] > 0), 'has_tech': int(c['n_tech'] > 0), 'has_signal': 0,
                'n_signals': 0, 'n_facts': 0, 'search_blob': ''})     # как gotovaya() загрузчика Базы 3; blob – на сервере
    izm, _ = E1.plan([dict(row)])
    for _, n, poch in izm:
        row.update(n)
    row['otrasl'] = otrasl(row['okved'])
    # --- «чей сайт» (D)
    ok, _, dok, sd = proverka_sayta(inn)
    row['proverka_sayta'] = 'свой'
    row['sayt_chey_ishodnyy'] = c.get('sayt_chey')
    row['sayt_chey'] = ('Проверка %s – свой: %s' % (DATA, '; '.join(dok)) +
                        (('. ' + ru['sayt_primechanie']) if ru.get('sayt_primechanie') else ''))[:1500]
    row['v_fajlah_meyer'] = 'файл 3'
    row['kachestvo_nomera'] = 'без ролей: настоящий мобильный'
    row['otkuda_kompaniya'] = 'замена помеченных 09.10 (fixG): файл 3, место %d в рейтинге отбора Базы 3' % kpo[inn]['mesto']
    # --- номера: строки Базы 3 + подписи со страницы + новые со своей страницы
    pr = ru.get('kontakty', {})
    for x in b3n[inn]:
        kk, dob = k10(x['value'])
        r = pr.get(kk + ('#' + dob if dob else ''), {})
        s = {'inn': inn, 'value': x['value'], 'kind': 'phone', 'person': r.get('person') or x['person'],
             'role': x['role'], 'position': r.get('position', '' if x['position'] == 'мобильный с сайта, без подписи' else x['position']),
             'phone_type': x['phone_type'], 'source': x['source'] + ' · сверено со страницей своего сайта 09.10 (fixG)',
             'source_url': r.get('source_url') or x['source_url'], 'fragment': x['fragment'], 'is_unknown_owner': 0,
             'vid_nomera': r.get('vid_nomera') or cat.vid_nomera_po_cifram(x['value']),
             'vid_pochemu': r.get('vid_pochemu') or '', 'rol_vruchnuyu': r.get('rol_vruchnuyu') or '',
             'podpis_stranicy': r.get('podpis_stranicy') or ''}
        kontakty.append(s)
    for n in ru.get('novye', []):
        vid = cat.vid_nomera_po_cifram(n['value'])
        kontakty.append({'inn': inn, 'value': n['value'], 'kind': 'phone', 'person': n.get('person') or None, 'role': '',
                         'position': n.get('position') or '',
                         'phone_type': vid if vid in ('мобильный', 'рабочий', 'рабочий с добавочным', '8-800') else 'рабочий',
                         'source': 'страница сайта · разбор подписей 09.10 (fixG): ' + n['pochemu'],
                         'source_url': n['source_url'], 'fragment': n.get('podpis_stranicy', '')[:400], 'is_unknown_owner': 0,
                         'vid_nomera': vid, 'vid_pochemu': '', 'rol_vruchnuyu': n.get('rol_vruchnuyu') or '',
                         'podpis_stranicy': n.get('podpis_stranicy') or ''})
    for p in ru.get('lyudi', []):
        rk = cat.rol_kontakta({'position': p['position']})
        lyudi.append({'inn': inn, 'person': p['person'], 'position': p['position'], 'role': rk['vid'], 'phone': '',
                      'phone_type': '', 'email': p.get('email', ''), 'source_url': p['source_url'],
                      'source': 'страница сайта · ЛПР без телефона, разбор 09.10 (fixG)', 'is_tech': rk['teh'],
                      'sprosit_u_priemnoy': p['sprosit_u_priemnoy']})
    if ru.get('holding'):
        holding = dict(ru['holding'])
        row['holding'], row['holding_gruppa'] = holding['nazvanie'], holding['gruppa']
    kompanii.append(row)

# роль каждого номера – той же функцией, что рисует карточку; старые колонки роли – по ней
for s in kontakty:
    rk = cat.rol_kontakta(s)
    s['is_purchaser'], s['is_tech'] = rk['zakup'], rk['teh']
    s['has_role'] = int(bool(rk['lpr']) or rk['vid'] in ('приёмная', 'общий номер', 'техслужба (не ЛПР)', 'без подписи'))
    s['nomer_ne_lichnyy'] = None if rk['lpr'] else rk['vid']
    if rk['lpr']:
        s['role'] = rk['vid']
    s['_rol'] = rk['vid']
    if s['person']:
        lyudi.append({'inn': s['inn'], 'person': s['person'], 'position': s['position'], 'role': s['role'], 'phone': s['value'],
                      'phone_type': s['phone_type'], 'email': '', 'source_url': s['source_url'], 'source': s['source'],
                      'is_tech': rk['teh'], 'sprosit_u_priemnoy': None})
    if rk['lpr'] and s['source_url']:
        istochniki.append({'inn': s['inn'], 'field_name': 'ЛПР: %s' % (s['position'] or rk['vid']), 'source': 'сайт компании',
                           'source_url': s['source_url']})

# ====================================================================== 3. СИМУЛЯЦИЯ: ступени и раздача
k = sqlite3.connect(os.path.join(SIM, 'meyer_baza1.db'))
k.row_factory = sqlite3.Row
s_ = sqlite3.connect(os.path.join(SIM, 'centro_sales_meyer1.db'))
ubrat = [dict(r) for r in k.execute("select inn, predpriyatie, pometka_ocheredi, bazy from company "
                                    "where trim(coalesce(pometka_ocheredi,''))<>''")]
vlad = dict(s_.execute('select inn, username from company_assignment').fetchall())
for u in ubrat:
    u['prodavec'] = vlad.get(u['inn'])
poteri = collections.Counter(u['prodavec'] for u in ubrat)
dannye_do = E2.poschitat_vse(os.path.join(SIM, 'meyer_baza1.db'), cat, sales)   # до удаления 13
kol_c = {r[1] for r in k.execute('pragma table_info(company)')}
kol_k = {r[1] for r in k.execute('pragma table_info(contact)')}
kol_p = {r[1] for r in k.execute('pragma table_info(person)')}
for t in ('company', 'contact', 'person', 'company_source', 'holding_chlen'):
    k.execute('delete from %s where inn in (%s)' % (t, ','.join('?' * len(ubrat))), [u['inn'] for u in ubrat])
for r in kompanii:
    rr = {kk: v for kk, v in r.items() if kk in kol_c}
    k.execute('insert into company (%s) values (%s)' % (','.join('"%s"' % x for x in rr), ','.join('?' * len(rr))), list(rr.values()))
for x in kontakty:
    rr = {kk: v for kk, v in x.items() if kk in kol_k}
    k.execute('insert into contact (%s) values (%s)' % (','.join(rr), ','.join('?' * len(rr))), list(rr.values()))
for x in lyudi:
    rr = {kk: v for kk, v in x.items() if kk in kol_p}
    k.execute('insert into person (%s) values (%s)' % (','.join(rr), ','.join('?' * len(rr))), list(rr.values()))
k.commit()
dannye = E2.poschitat_vse(os.path.join(SIM, 'meyer_baza1.db'), cat, sales)
novye = {inn: dannye[inn] for inn in SEL}
for inn in SEL:
    d = novye[inn]
    print('   %s %-34s ступень %d  важность %5.1f  балл %6.1f  выручка %4.0f млн' % (
        inn, kpo[inn]['nazvanie'][:34], E2.STUPEN[d['tier']], d['ball'], d['score'], (d['vyr'] or 0) / 1e6))
ostalis = {i: u for i, u in vlad.items() if i not in {x['inn'] for x in ubrat}}
t_do, ch_do = E2.tablica(vlad, dannye_do, 'ДО (с 13 помеченными)')
# принудительно: холдинг
prinud = {}
if holding:
    for i in holding['chleny']:
        if i in ostalis:
            for j in holding['chleny']:
                if j in SEL:
                    prinud[j] = ostalis[i]
ostatok = {p: poteri[p] - sum(1 for j, q in prinud.items() if q == p) for p in E2.PRODAVCY}
svobodnye = [i for i in SEL if i not in prinud]
print('потери продавцов: %s; принудительно (холдинг): %s; осталось раздать: %s' % (dict(poteri), prinud, ostatok))


METR = ('t4', 't3', 't2', 't1', 't0', 'lpr_fio', 'tech', 'klient_sc', 'bitrix')
FUN = [next(f for k_, _, f in E2.POKAZATELI if k_ == kl) for kl in METR]
baza = dict(ostalis)
baza.update(prinud)
B_SCH = {p: [0] * len(METR) for p in E2.PRODAVCY}
B_VYR = {p: [] for p in E2.PRODAVCY}
B_SC = {p: [0.0, 0] for p in E2.PRODAVCY}
for i, p in baza.items():
    r = dannye[i]
    for n_, f in enumerate(FUN):
        B_SCH[p][n_] += f(r)
    if r['vyr'] is not None:
        B_VYR[p].append(r['vyr'])
    B_SC[p][0] += r['score']
    B_SC[p][1] += 1
for p in E2.PRODAVCY:
    B_VYR[p].sort()
VEK = {i: [f(dannye[i]) for f in FUN] for i in SEL}


def ocenka_bystro(kl):
    """То же, что сравнение таблиц E2: разброс ступеней, прочих показателей, медианы выручки, среднего балла."""
    import bisect
    sch = {p: list(B_SCH[p]) for p in E2.PRODAVCY}
    vyr = {p: B_VYR[p] for p in E2.PRODAVCY}
    sc = {p: list(B_SC[p]) for p in E2.PRODAVCY}
    kop = set()
    for i, p in kl.items():
        for n_, v in enumerate(VEK[i]):
            sch[p][n_] += v
        if dannye[i]['vyr'] is not None:
            if p not in kop:
                vyr[p] = list(vyr[p])
                kop.add(p)
            bisect.insort(vyr[p], dannye[i]['vyr'])
        sc[p][0] += dannye[i]['score']
        sc[p][1] += 1
    razb = [max(sch[p][n_] for p in E2.PRODAVCY) - min(sch[p][n_] for p in E2.PRODAVCY) for n_ in range(len(METR))]
    med = [E2.mediana(vyr[p]) / 1e6 for p in E2.PRODAVCY]
    sr = [sc[p][0] / max(1, sc[p][1]) for p in E2.PRODAVCY]
    return (sum(razb[:5]), sum(razb[5:]), round(max(med) - min(med), 1), round(max(sr) - min(sr), 2))


luchshee = None
vidano = [0]


def varianty(j, ost):
    """Все раскладки свободных компаний по продавцам с заданной ёмкостью (без повторов)."""
    if j == len(svobodnye):
        yield {}
        return
    for p in E2.PRODAVCY:
        if ost[p] > 0:
            ost[p] -= 1
            for v in varianty(j + 1, ost):
                v[svobodnye[j]] = p
                yield v
            ost[p] += 1


for kl in varianty(0, dict(ostatok)):
    vidano[0] += 1
    o = ocenka_bystro(kl)
    if luchshee is None or o < luchshee[0]:
        luchshee = (o, dict(kl))
o, kl = luchshee
raspr = dict(baza)
raspr.update(kl)
print('вариантов перебрано %d; лучшая оценка (разброс ступеней, прочих, медианы, балла): %s' % (vidano[0], o))
t_bez, _ = E2.tablica(ostalis, dannye, 'БЕЗ 13 помеченных (до замены)')
t_po, ch_po = E2.tablica(raspr, dannye, 'ПОСЛЕ замены')
print(t_do)
print(t_bez)
print(t_po)
prodavcy = {i: raspr[i] for i in SEL}
plan = {'vremya': time.strftime('%Y%m%d-%H%M%S'), 'ubrat': ubrat, 'poteri': dict(poteri),
        'otobrano': otobrano, 'otkaz': otkaz, 'zapas': zapas,
        'kompanii': kompanii, 'kontakty': [{kk: v for kk, v in x.items() if not kk.startswith('_')} for x in kontakty],
        'lyudi': lyudi, 'istochniki': istochniki, 'holding': holding, 'prodavcy': prodavcy,
        'stupeni': {i: {'tier': novye[i]['tier'], 'ball': novye[i]['ball'], 'score': novye[i]['score'],
                        'pochemu': novye[i]['pochemu']} for i in SEL},
        'tablica_do': t_do, 'tablica_bez': t_bez, 'tablica_posle': t_po}
io.open(OUT, 'w', encoding='utf-8').write(json.dumps(plan, ensure_ascii=False, indent=1))
print('план: %s; продавцы новых: %s' % (OUT, collections.Counter(prodavcy.values())))
