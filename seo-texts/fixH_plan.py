# -*- coding: utf-8 -*-
"""fixH (локально): выгрузка сделок Битрикса 09.10 (владелец: «если есть активные сейчас в базе (сделка Meyer
в работе) – выкинь их», «добери до 150 у каждого», поля Битрикса для всех 600).

1. УБРАТЬ – компании панели с активной сделкой Meyer (АКТИВНА = да в meyer_all.csv): по ИНН сделки, по ИНН компании
   в тексте сделки, по точному названию у сделок без ИНН – каждое совпадение по названию проверено глазами
   (список координатора 28 + найденная при перепроверке «Полинка»). Сверка – fixH_bitrix_sverka.py -> sverka.json;
   доказательства по названию – po_imeni_sdelki.json (строки сделок, прочитанные скриптом).
2. ДОБОР до 150 у каждого – источники по порядку: остаток файла 6 (места после 14, на которых остановился fixG3),
   потом остаток файла 2, потом файл 3 с правилом «название + город = свой сайт»; к следующему – только если в
   предыдущем годных нет. Требования прежние (fixG3): действующая по checko, основной ОКВЭД даёт сегмент,
   выручка от 100 млн, сайт доказанно свой (ИНН/ОГРН/руководитель/юрадрес из checko), настоящий мобильный
   сейчас на странице своего сайта, не Воронеж; плюс НЕТ активной сделки Meyer (по ИНН, ИНН в тексте,
   точному названию). Порядок – ЛПР с личным номером, потом балл файла (ЛПР подписанных на своих сайтах
   проверены в fixG3 – личного номера ни у кого; см. LPR_NE_LICHNYY).
3. ПОЛЯ БИТРИКСА для всех итоговых 600 (sverka.json): bitrix_kc 1/0, bitrix_kc_info «сделок N: воронка ×k, …»,
   bitrix_sdelok, bitrix_klient_sc, bitrix_klient_meyer, bitrix_v_rabote, bitrix_poslednyaya, bitrix_istochnik;
   прежний bitrix_kc_info – в bitrix_kc_info_ishodnoe (это делает загрузчик на сервере).
4. РАЗДАЧА – MILP fixG2/fixG3 (холдинги целиком, краснодарские только у Ерохина/Беляева поровну, по 150,
   показатели E2 в коридорах – уже с НОВЫМИ полями Битрикса, плюс клиенты Meyer и «в работе у КЦ/СЦ»),
   цель – минимум перемещений; компании с действиями продавцов не двигаются.

    python3 fixH_plan.py <папка fixH> <выход plan.json>
"""
import collections
import gzip
import io
import json
import os
import re
import shutil
import sqlite3
import sys
import time

W2, OUT = sys.argv[1:3]
ZDES = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ZDES)
DATA = time.strftime('%d.%m.%Y')
SIM = os.path.join(W2, 'sim')
os.makedirs(SIM, exist_ok=True)
for f in ('meyer_baza1.db', 'centro_sales_meyer1.db'):
    shutil.copy(os.path.join(W2, 'db0', f), os.path.join(SIM, f))
os.environ['CENTRIFUGAL_DB'] = os.environ['CENTRO_DB'] = os.path.join(SIM, 'meyer_baza1.db')
os.environ['CENTRO_SALES_DB'] = os.path.join(SIM, 'centro_sales_meyer1.db')
sys.path.insert(0, os.path.join(W2, 'kodroot'))
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
    return json.load(open(os.path.join(W2, p), encoding='utf-8'))


kand = zagr('f6/kandidaty.json')
b3 = zagr('f6/meyer-fixG3-f6.json')   # строки скрипта Базы 6
razbor = zagr('checko/razbor.json')
svyazi = zagr('checko/svyazi.json')
chey = zagr('f6/chey_vse.json')
SVERKA = zagr('sverka.json')
PO_IMENI = zagr('po_imeni_sdelki.json')
KOORD = zagr('ubrat-aktivnye-meyer.json')
ruchnye = zagr('fixH-ruchnye.json')
indeks = zagr('pages/_indeks.json')
ISTOCHNIK_BITRIX = 'выгрузка Битрикса 09.10'

# ручные отказы (проверено по страницам 09.10; первые два – из fixG3)
RUCHNO_OTKAZ = {
    '2373015878': 'оператор сайта vmzav.ru по политике конфиденциальности – ИП Онисич Н. А. (ИНН 233000771229), другое лицо '
                  '(учредитель ООО по checko – Куткова О. Н.); совпадает только юрадрес – сайт не доказанно свой',
    '2373017466': 'сайт – мини-сайт Яндекс Карт («Сайт создан в…», номер «Показать») на kub-ptica.clients.site; правило Базы 3: '
                  'не мини-сайт справочника',
}
RUCHNO_OTKAZ.update(ruchnye.get('_otkaz', {}))
# ЛПР со страниц своих сайтов (fixG3_lpr_skan.py), проверено глазами 09.10: номер не личный номер ЛПР
LPR_NE_LICHNYY = {
    '1686021074': 'мобильный под строкой реквизитов «Генеральный директор Байрамова Н. Ш.» – это общий номер «Свяжитесь с нами» (info@)',
    '5638068915': 'мобильный в реквизитах подписан «Бухгалтерия», а не директором',
    '6125031566': '«Отдел закупок» – закупка КРС у поставщиков (закупки сырья, не ЛПР)',
    '4716003024': 'у генерального директора указан многоканальный номер завода (общий), личная только почта',
    '5018167458': 'номер под строкой реквизитов директора – общий номер компании; доб. 107 – отдел кадров',
    '7116148802': 'тульский офисный номер «по вопросам качества продукции и поставок сырья и оборудования» – общий, не личный',
    '6102000995': '«Отдел гос. закупок» с кнопкой «Заказать» – продажи госзаказчикам, не снабжение',
    '2465325125': '«Владельцу сайта» – не должность',
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
            t, _ = R.html_v_tekst(R.dekodirovat(gzip.open(os.path.join(W2, 'pages', z['fajl'])).read(), z.get('tip', '')))
            res = {'t': t, 'vh': R.nomera_v_tekste(t)}
        _kesh[url] = res
    return _kesh[url]


def k10(v):
    osn, dob = cat._razdelit_dobavochnyy(v)
    return R.klyuch10(R.cifry(osn)), dob


# «настоящий мобильный» – как meyer_baza3_v_json.nastoyashchiy_mobilnyy (в fixG3 флаг файла 6 ставился любому номеру
# со своего сайта – ошибка, найдена в fixH: здесь проверяется именно мобильный)
MINISAYT = re.compile(r'Сайт создан в|Показать|Как доехать', re.I)
DILER = re.compile(r'дилер|партн[её]р|представител|филиал\w* в', re.I)
STUDIYA = re.compile(r'разработ\w* сайт|создани\w* сайт|сайт (?:сделан|создан)|веб-?студ|продвижени|seo|хостинг|digital', re.I)
ORG = re.compile(r'(?:ООО|АО|ЗАО|ПАО|ОАО|ИП)\s*[«"]\s*([^»"]{2,40})', re.I)


def shablon(c):
    return bool((not c.startswith('9')) or len(set(c)) <= 2 or re.search(r'(\d)\1{5}', c)
                or '1234567' in c or c.endswith('0000000'))


def nastoyashchiy_mobilnyy(n, sd):
    kk = k10(n['nomer'])[0]
    f = n.get('fragment') or ''
    if not n.get('svoy') or cat.vid_nomera_po_cifram(n['nomer']) != 'мобильный' or not kk or shablon(kk):
        return False
    dn = domen(n['url'])
    if not sd or not (dn == sd or dn.endswith('.' + sd)):
        return False
    if MINISAYT.search(f) or DILER.search(f) or STUDIYA.search(f):
        return False
    return len({m.strip().lower() for m in ORG.findall(f)}) <= 1


def mobilnyy_na_stranice(c, sd):
    """Настоящий мобильный сейчас стоит на странице своего домена."""
    stranicy = [u for u, z in indeks.items() if domen(u) == sd and z.get('kod') == 200]
    for n in c['nomera']:
        if not nastoyashchiy_mobilnyy(n, sd):
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


def bitrix_polya(inn):
    """Поля Битрикса из сверки (панель или кандидат) – как пишет загрузчик."""
    x = SVERKA['panel'].get(inn) or SVERKA['kandidaty'].get(inn)
    if x is None:
        raise SystemExit('ИНН %s нет в сверке с Битриксом – перезапусти fixH_bitrix_sverka.py с кандидатами' % inn)
    p = {kk: x[kk] for kk in ('bitrix_kc', 'bitrix_kc_info', 'bitrix_sdelok', 'bitrix_klient_sc', 'bitrix_klient_meyer',
                              'bitrix_v_rabote', 'bitrix_poslednyaya')}
    p['bitrix_istochnik'] = ISTOCHNIK_BITRIX
    return p


def aktivnaya_meyer(inn):
    x = SVERKA['panel'].get(inn) or SVERKA['kandidaty'].get(inn) or {}
    return x.get('aktivnye_meyer') or [], x.get('po_imeni_proverit') or []


def kratko_sdelki(a):
    return 'сделка %s %s «%s» от %s: %s' % (a['id'], a['voronka'], a['stadiya'], a['data'], (a.get('title') or a.get('kompaniya') or '')[:90])


# ====================================================================== 0. КОГО УБРАТЬ
DOP_UBRAT = {
    '7721691131': 'перепроверка fixH: у сделки нет ИНН, название «Полинка» отличительное, и совпал профиль: в сделке «основная '
                  'продукция – каши быстрого приготовления в упаковке», у компании (polinka.online) – «производство каш '
                  'моментального приготовления», офисы в Рязани и Москве, производство в с. Кораблино Рязанской обл.',
}
ubrat_inn = list(dict.fromkeys(KOORD['po_inn'] + list(KOORD['inn_v_nazvanii_sdelki']) + list(KOORD['po_tochnomu_nazvaniyu'])
                               + list(DOP_UBRAT)))
dokaz = {}
for inn in ubrat_inn:
    akt, imya = aktivnaya_meyer(inn)
    d = []
    for a in akt:
        d.append('%s: %s' % (a['kak'], kratko_sdelki(a)))
    if not d:
        for a in PO_IMENI.get(inn, []):
            if a['aktivna'] == 'да' and a['voronka'].startswith('MEYER'):
                d.append('точное название (у сделки нет ИНН, проверено глазами): %s' % kratko_sdelki(a))
        if inn in DOP_UBRAT:
            d.append(DOP_UBRAT[inn])
        elif inn in KOORD['po_tochnomu_nazvaniyu']:
            d.append('координатор: ' + KOORD['po_tochnomu_nazvaniyu'][inn])
    if not d:
        raise SystemExit('нет доказательства для %s' % inn)
    dokaz[inn] = list(dict.fromkeys(d))

# ====================================================================== 1. ОТБОР (остаток файла 6)
VOR, KRD = 'Воронежская область', 'Краснодарский край'
NACHALO, NUZHNO = 14, len(ubrat_inn)
ks = sqlite3.connect(os.path.join(SIM, 'meyer_baza1.db'))
v_paneli = {r[0] for r in ks.execute('SELECT inn FROM company')}
ubrany = {r[0] for r in ks.execute('SELECT inn FROM arhiv_company')} | set(ubrat_inn)
ks.close()
otobrano, otkaz = [], []
for c in kand:
    if c['mesto'] <= NACHALO:
        continue
    if len(otobrano) >= NUZHNO:
        break
    inn = c['inn']
    z = razbor.get(inn) or {}
    prich = []
    region = E1.subekt_adresa(z.get('adres'))[0] or E1.region_norm(c['region'])
    if inn in v_paneli and inn not in ubrat_inn:
        prich.append('уже в панели')
    if inn in ubrany:
        prich.append('убрана из панели 09.10')
    if region == VOR:
        prich.append('Воронежская область – по решению владельца 09.10 не берём')
    akt, imya = aktivnaya_meyer(inn)
    if akt:
        prich.append('активная сделка Meyer: ' + '; '.join(kratko_sdelki(a) for a in akt))
    elif imya:
        prich.append('возможна активная сделка Meyer по названию (не проверено): ' + '; '.join(kratko_sdelki(a) for a in imya))
    if not z:
        prich.append('страница checko не скачивалась')
    elif z.get('oshibka'):
        prich.append('checko: ' + z['oshibka'])
    else:
        if 'Действующ' not in (z.get('status') or ''):
            prich.append('статус по checko: %s' % z.get('status'))
        v = z.get('vyruchka')
        if v is None or float(v) < 1e8:
            prich.append('выручка по checko %s млн за %s – меньше 100' % (round(v / 1e6) if v else '?', z.get('fin_god')))
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
           'region': region, 'krasnodar': region == KRD, 'vyruchka_checko': z.get('vyruchka'), 'status': z.get('status'),
           'sayt': sd, 'dokaz': dok, 'prichiny': prich, 'istochnik': 'файл 6'}
    (otkaz if prich else otobrano).append(zap)
posledniy = max(c['mesto'] for c in kand)
proveren_do = max([x['mesto'] for x in otobrano + otkaz] or [NACHALO])
print('убрать (активная сделка Meyer): %d; остаток файла 6: в рейтинге %d мест, проверены %d–%d; отобрано %d (места %s), отбраковано %d' % (
    len(ubrat_inn), len(kand), NACHALO + 1, proveren_do, len(otobrano), [x['mesto'] for x in otobrano], len(otkaz)))
if len(otobrano) < NUZHNO:
    print('НЕ НАБРАЛОСЬ %d из %d в остатке файла 6 (последнее место %d) – нужен следующий источник (остаток файла 2)' % (
        NUZHNO - len(otobrano), NUZHNO, posledniy))
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
    # --- регион, пояс, сегмент, попадание, пометка (E1); Битрикс – новая выгрузка (как загрузчик)
    for kk in E1_KOL:
        row.setdefault(kk, None)
    row['bitrix_kc'] = 0
    row.update({'has_purchaser': int(c['n_purchaser'] > 0), 'has_tech': int(c['n_tech'] > 0), 'has_signal': 0,
                'n_signals': 0, 'n_facts': 0, 'search_blob': ''})     # как gotovaya() загрузчика Базы 3; blob – на сервере
    izm, _ = E1.plan([dict(row)])
    for _, n, poch in izm:
        row.update(n)
    row.update(bitrix_polya(inn))
    row['otrasl'] = otrasl(row['okved'])
    # --- «чей сайт» (D)
    ok, _, dok, sd = proverka_sayta(inn)
    row['proverka_sayta'] = 'свой'
    row['sayt_chey_ishodnyy'] = c.get('sayt_chey')
    row['sayt_chey'] = ('Проверка %s – свой: %s' % (DATA, '; '.join(dok)) +
                        (('. ' + ru['sayt_primechanie']) if ru.get('sayt_primechanie') else ''))[:1500]
    row['v_fajlah_meyer'] = c.get('v_fajlah_meyer') or ''
    row['holding'], row['holding_gruppa'] = '', ''   # группы файла 6 – не панели; связи с панелью нет
    row['otkuda_kompaniya'] = ('добор до 150 09.10 (fixH, замена компаний с активной сделкой Meyer): остаток файла 6, '
                               'место %d (балл файла %.1f); %s' % (kpo[inn]['mesto'], kpo[inn]['reyting'],
                                                                   c.get('otkuda_kompaniya') or '')).strip('; ')
    # --- номера: строки Базы 6 + подписи со страницы + новые со своей страницы
    pr = ru.get('kontakty', {})
    for x in b3n[inn]:
        kk, dob = k10(x['value'])
        r = pr.get(kk + ('#' + dob if dob else ''), {})
        if r.get('ne_brat'):
            zhurnal_plana.append({'inn': inn, 'ne_vzyat_nomer': x['value'], 'pochemu': r['ne_brat']})
            continue
        dn = domen(x['source_url'])
        if not dn or not (dn == sd or dn.endswith('.' + sd)):
            zhurnal_plana.append({'inn': inn, 'ne_vzyat_nomer': x['value'], 'pochemu': 'номер не со страницы своего сайта (%s)' % (dn or 'без ссылки')})
            continue
        if not any(st and any(v_['k10'] == kk for v_ in st['vh']) for st in (
                stranica(u_) for u_ in [x['source_url']] + [u_ for u_, z_ in indeks.items() if domen(u_) == sd and z_.get('kod') == 200])):
            zhurnal_plana.append({'inn': inn, 'ne_vzyat_nomer': x['value'], 'pochemu': 'номера 09.10 на страницах своего сайта уже нет'})
            continue
        s = {'inn': inn, 'value': x['value'], 'kind': 'phone', 'person': (r['person'] or None) if 'person' in r else x['person'],
             'role': x['role'], 'position': r.get('position', '' if x['position'] == 'мобильный с сайта, без подписи' else x['position']),
             'phone_type': x['phone_type'], 'source': x['source'] + ' · сверено со страницей своего сайта 09.10 (fixH)',
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
                         'source': 'страница сайта · разбор подписей 09.10 (fixH): ' + n['pochemu'],
                         'source_url': n['source_url'], 'fragment': n.get('podpis_stranicy', '')[:400], 'is_unknown_owner': 0,
                         'vid_nomera': vid, 'vid_pochemu': '', 'rol_vruchnuyu': n.get('rol_vruchnuyu') or '',
                         'podpis_stranicy': n.get('podpis_stranicy') or ''})
    for p in ru.get('lyudi', []):
        rk = cat.rol_kontakta({'position': p['position']})
        lyudi.append({'inn': inn, 'person': p['person'], 'position': p['position'], 'role': rk['vid'], 'phone': '',
                      'phone_type': '', 'email': p.get('email', ''), 'source_url': p['source_url'],
                      'source': 'страница сайта · ЛПР без телефона, разбор 09.10 (fixH)', 'is_tech': rk['teh'],
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


# ====================================================================== 3. СИМУЛЯЦИЯ И РАЗДАЧА
import numpy as np  # noqa: E402
from scipy.optimize import Bounds, LinearConstraint, milp  # noqa: E402

PRODAVCY = E2.PRODAVCY
FIO = {'meyer1': 'Пяткова', 'meyer2': 'Ерохин', 'meyer3': 'Беляев', 'meyer4': 'Волков'}
KRD_PRODAVCY = ['meyer2', 'meyer3']
k = sqlite3.connect(os.path.join(SIM, 'meyer_baza1.db'))
k.row_factory = sqlite3.Row
s_ = sqlite3.connect(os.path.join(SIM, 'centro_sales_meyer1.db'))
vlad = dict(s_.execute('SELECT inn, username FROM company_assignment').fetchall())
zakrep = set()
for t in ('company_state', 'company_comment', 'zvonok_sobytie', 'activity_log', 'hidden_item'):
    try:
        zakrep |= {str(r[0]) for r in s_.execute('SELECT DISTINCT inn FROM %s WHERE inn IS NOT NULL' % t)}
    except sqlite3.OperationalError:
        pass
kat_do = {r['inn']: dict(r) for r in k.execute('SELECT inn, predpriyatie, region, bazy, okved, holding_gruppa FROM company')}
ostavleny = [dict(kat_do[i], dokaz=dokaz[i]) for i in ubrat_inn if i in zakrep]
nety = [i for i in ubrat_inn if i not in kat_do]
assert not nety, 'убираемых нет в каталоге: %s' % nety
ubrat = [dict(kat_do[i], prodavec=vlad.get(i), dokaz=dokaz[i]) for i in ubrat_inn if i not in zakrep]
print('убрать %d: по продавцам %s; оставить (есть действия продавцов) %d %s' % (
    len(ubrat), dict(collections.Counter(FIO[u['prodavec']] for u in ubrat)), len(ostavleny), [c['inn'] for c in ostavleny]))
hold_ubr = [(u['inn'], u['holding_gruppa']) for u in ubrat if u.get('holding_gruppa')]
if hold_ubr:
    print('убираемые в группах холдингов: %s' % hold_ubr)
dannye_do = E2.poschitat_vse(os.path.join(SIM, 'meyer_baza1.db'), cat, sales)
bitrix_do = {r['inn']: dict(r) for r in k.execute('SELECT inn, bitrix_kc, bitrix_kc_info, bitrix_sdelok, bitrix_klient_sc FROM company')}
region_do = {r[0]: r[1] for r in k.execute('SELECT inn, region FROM company')}
kol_c = {r[1] for r in k.execute('pragma table_info(company)')}
kol_k = {r[1] for r in k.execute('pragma table_info(contact)')}
kol_p = {r[1] for r in k.execute('pragma table_info(person)')}
for t in ('company', 'contact', 'person', 'company_source', 'holding_chlen'):
    if ubrat:
        k.execute('delete from %s where inn in (%s)' % (t, ','.join('?' * len(ubrat))), [u['inn'] for u in ubrat])


def k10_(v):
    return R.klyuch10(R.cifry(cat._razdelit_dobavochnyy(v)[0]))


# общие номера новых с компаниями панели (до вставки)
nomera_paneli = collections.defaultdict(set)
for r in k.execute("SELECT inn, value FROM contact WHERE kind='phone'"):
    if k10_(r['value']):
        nomera_paneli[k10_(r['value'])].add(r['inn'])
obshchie_novyh = []
for x in kontakty:
    kk = k10_(x['value'])
    if kk and nomera_paneli.get(kk):
        obshchie_novyh.append({'inns': sorted(nomera_paneli[kk] | {x['inn']}), 'nomer_k10_hvost': kk[-4:]})
# общие номера между самими новыми
nomera_novyh = collections.defaultdict(set)
for x in kontakty:
    kk = k10_(x['value'])
    if kk:
        nomera_novyh[kk].add(x['inn'])
for kk, inns in nomera_novyh.items():
    if len(inns) > 1:
        obshchie_novyh.append({'inns': sorted(inns), 'nomer_k10_hvost': kk[-4:]})
print('общих номеров у новых с компаниями панели и между собой: %d %s' % (len(obshchie_novyh), obshchie_novyh))
for c in ('bitrix_klient_meyer', 'bitrix_v_rabote', 'bitrix_poslednyaya', 'bitrix_istochnik', 'bitrix_kc_info_ishodnoe'):
    if c not in kol_c:
        k.execute('ALTER TABLE company ADD COLUMN %s %s' % (c, 'TEXT' if c in ('bitrix_poslednyaya', 'bitrix_istochnik', 'bitrix_kc_info_ishodnoe') else 'INTEGER'))
        kol_c.add(c)
for r in kompanii:
    rr = {kk: v for kk, v in r.items() if kk in kol_c}
    k.execute('insert into company (%s) values (%s)' % (','.join('"%s"' % x for x in rr), ','.join('?' * len(rr))), list(rr.values()))
for x in kontakty:
    rr = {kk: v for kk, v in x.items() if kk in kol_k}
    k.execute('insert into contact (%s) values (%s)' % (','.join(rr), ','.join('?' * len(rr))), list(rr.values()))
for x in lyudi:
    rr = {kk: v for kk, v in x.items() if kk in kol_p}
    k.execute('insert into person (%s) values (%s)' % (','.join(rr), ','.join('?' * len(rr))), list(rr.values()))
# поля Битрикса – всем итоговым (как загрузчик): прежний bitrix_kc_info -> bitrix_kc_info_ishodnoe
BITRIX = {}
for (inn,) in k.execute('SELECT inn FROM company').fetchall():
    p = bitrix_polya(inn)
    BITRIX[inn] = p
    k.execute('UPDATE company SET bitrix_kc_info_ishodnoe=COALESCE(bitrix_kc_info_ishodnoe, bitrix_kc_info) WHERE inn=?', (inn,))
    k.execute('UPDATE company SET %s WHERE inn=?' % ', '.join('"%s"=?' % kk for kk in p), list(p.values()) + [inn])
k.commit()
dannye = E2.poschitat_vse(os.path.join(SIM, 'meyer_baza1.db'), cat, sales)
region = {r[0]: r[1] for r in k.execute('SELECT inn, region FROM company')}
naim = {r[0]: r[1] for r in k.execute('SELECT inn, predpriyatie FROM company')}
for inn in SEL:
    d = dannye[inn]
    print('   %s %-34s %-24s ступень %d  важность %5.1f  балл %6.1f  выручка %5.0f млн  Битрикс %s' % (
        inn, naim[inn][:34], region[inn][:24], E2.STUPEN[d['tier']], d['ball'], d['score'], (d['vyr'] or 0) / 1e6,
        BITRIX[inn]['bitrix_kc_info'] or '–'))
for i in dannye:
    dannye[i]['klient_meyer'] = int(BITRIX[i]['bitrix_klient_meyer'] or 0)
    dannye[i]['v_rabote'] = int((BITRIX[i]['bitrix_v_rabote'] or 0) > 0)

# единицы раздачи: группы fixD + группы каталога gG-… + общие номера новых
hold = zagr('fixD-holdingi.json')
for g in {r[0] for r in k.execute("SELECT DISTINCT gruppa FROM holding_chlen WHERE gruppa LIKE 'gG-%'")}:
    hold['gruppy'][g] = {'nazvanie': g}
    for r in k.execute('SELECT inn FROM holding_chlen WHERE gruppa=?', (g,)):
        hold['inn_gruppa'][r[0]] = g
for o in obshchie_novyh:
    hold['obshchie_nomera_bez_svyazi'].append({'inns': o['inns'], 'nazvaniya': [naim.get(i, i) for i in o['inns']]})
vse = sorted(dannye)
edin, pochemu_ed = E2.edinicy_razdachi(hold, set(vse))
U = sorted(edin)
N = len(vse)
CEL = {p: N // 4 + (1 if n < N % 4 else 0) for n, p in enumerate(PRODAVCY)}
krd = {i for i in vse if region.get(i) == KRD}
K = len(krd)
print('после замены компаний %d -> по продавцам %s; краснодарских %d' % (N, CEL, K))
dop, konflikty = {}, []
for u in U:
    chl = edin[u]
    zak = {vlad[i] for i in chl if i in zakrep and i in vlad}
    est_krd = any(i in krd for i in chl)
    if zak:
        dop[u] = sorted(zak)[:1]
        if est_krd and dop[u][0] not in KRD_PRODAVCY:
            konflikty.append('краснодарская группа %s с действиями у %s – остаётся у него' % (chl, dop[u][0]))
    elif est_krd:
        dop[u] = list(KRD_PRODAVCY)
    else:
        dop[u] = list(PRODAVCY)
idx = {}
for u in U:
    for p in dop[u]:
        idx[(u, p)] = len(idx)
nx = len(idx)
cost = np.zeros(nx)
for (u, p), j in idx.items():
    cost[j] = sum(1 for i in edin[u] if i in vlad and vlad[i] != p)
metriki = [(kl, f) for kl, _, f in E2.POKAZATELI if kl not in ('lpr_mob_vse', 't0')]
metriki.append(('lpr_mob_vse', lambda r: int(r['tier'] in (3, 4))))
metriki.append(('klient_meyer', lambda r: r['klient_meyer']))
metriki.append(('v_rabote', lambda r: r['v_rabote']))
vy = sorted(dannye[i]['vyr'] for i in vse if dannye[i]['vyr'])
porogi = [vy[int(len(vy) * q)] for q in (0.25, 0.4, 0.46, 0.48, 0.5, 0.52, 0.54, 0.6, 0.75)]
metriki.append(('vyr_net', lambda r: int(not r['vyr'])))
for n_t, t in enumerate(porogi):
    metriki.append(('vyr_nizhe%d' % n_t, (lambda tt: (lambda r: int(bool(r['vyr']) and r['vyr'] < tt)))(t)))
STUPENI = {'t4', 't3', 't2', 't1', 'lpr_mob_vse'}


def polosa(tot, w):
    """Коридор числа у продавца: w=1 – floor/ceil(tot/4) (разница не больше 1); w=2 – ceil-1..ceil+1 (не больше 2)."""
    if w <= 1:
        return tot // 4, -(-tot // 4)
    lo = -(-tot // 4) - (w // 2)
    return lo, lo + w


def reshit(zapas_stup, zapas_proch, koridor):
    A, lo, hi = [], [], []
    for u in U:
        row = np.zeros(nx)
        for p in dop[u]:
            row[idx[(u, p)]] = 1
        A.append(row); lo.append(1); hi.append(1)
    for p in PRODAVCY:
        row = np.zeros(nx)
        for u in U:
            if (u, p) in idx:
                row[idx[(u, p)]] = len(edin[u])
        A.append(row); lo.append(CEL[p]); hi.append(CEL[p])
    for p in KRD_PRODAVCY:
        row = np.zeros(nx)
        for u in U:
            if (u, p) in idx:
                row[idx[(u, p)]] = sum(1 for i in edin[u] if i in krd)
        A.append(row); lo.append(K // 2); hi.append(-(-K // 2))
    for kl, f in metriki:
        tot = sum(f(dannye[i]) for i in vse)
        a, b = polosa(tot, zapas_stup if kl in STUPENI else zapas_proch)
        for p in PRODAVCY:
            row = np.zeros(nx)
            for u in U:
                if (u, p) in idx:
                    row[idx[(u, p)]] = sum(f(dannye[i]) for i in edin[u])
            A.append(row); lo.append(a); hi.append(b)
    sr = sum(dannye[i]['score'] for i in vse) / N
    for p in PRODAVCY:
        row = np.zeros(nx)
        for u in U:
            if (u, p) in idx:
                row[idx[(u, p)]] = sum(dannye[i]['score'] for i in edin[u])
        A.append(row); lo.append((sr - koridor) * CEL[p]); hi.append((sr + koridor) * CEL[p])
    return milp(cost, constraints=LinearConstraint(np.array(A), lo, hi), integrality=np.ones(nx),
                bounds=Bounds(0, 1), options={'time_limit': 240})


# варианты: разница по ступеням (800/600/400/200 и «ЛПР с мобильным всего») не больше 1 или 2, по прочим
# показателям – не больше 1/2/3, средний балл очереди в коридоре ±2..±5; берётся самый строгий вариант,
# который стоит не больше чем на 3 перемещения дороже самого дешёвого
VARIANTY = [(1, 1, 2), (1, 2, 3), (1, 3, 3), (2, 2, 3), (2, 3, 5)]
reshennye = []
for zs, zp, kor in VARIANTY:
    res = reshit(zs, zp, kor)
    ok_ = res.x is not None and res.status in (0, 1)
    print('MILP: разница ступеней <=%d, прочих <=%d, средний балл ±%d: %s, перемещений %s' % (
        zs, zp, kor, res.message[:40], round(res.fun) if ok_ else '–'))
    if ok_:
        reshennye.append((round(res.fun), VARIANTY.index((zs, zp, kor)), res, zs, zp, kor))
if not reshennye:
    raise SystemExit('раскладка не найдена')
mn = min(x[0] for x in reshennye)
_, _, res, zs, zp, kor = min((x for x in reshennye if x[0] <= mn + 3), key=lambda x: x[1])
print('выбран вариант: ступени <=%d, прочие <=%d, балл ±%d' % (zs, zp, kor))
novoe = {}
for (u, p), j in idx.items():
    if res.x[j] > 0.5:
        for i in edin[u]:
            novoe[i] = p
for u in U:
    assert len({novoe[i] for i in edin[u]}) == 1, edin[u]
peremeshcheniya = []
for i in vse:
    if i in vlad and novoe[i] != vlad[i]:
        u = next(uu for uu in U if i in edin[uu])
        if i in krd:
            prich = 'краснодарские – только у Ерохина и Беляева (владелец 09.10)'
        else:
            prich = 'выравнивание качества очередей при замене компаний с активной сделкой Meyer'
        if len(edin[u]) > 1:
            prich += '; группа целиком: ' + '; '.join(sorted(pochemu_ed.get(i, [])))[:200]
        peremeshcheniya.append({'inn': i, 'nazvanie': naim[i], 'region': region[i], 'ot': vlad[i], 'komu': novoe[i],
                                'prichina': prich, 'stupen': E2.STUPEN[dannye[i]['tier']]})
prodavcy = {i: novoe[i] for i in SEL}
vlad_do = {i: u for i, u in vlad.items() if i in dannye_do}
t_do, _ = E2.tablica(vlad_do, dannye_do, 'ДО (сейчас, Битрикс – прежний справочник)')
t_po, _ = E2.tablica(novoe, dannye, 'ПОСЛЕ (убрано %d, добрано %d; Битрикс – выгрузка 09.10)' % (len(ubrat), len(SEL)))
print(t_do)
print(t_po)
# Битрикс до/после (компаний): галочка, клиенты Meyer, клиенты СЦ, с активными сделками КЦ/СЦ
def bx_schet(raspr, f):
    return {FIO[p]: sum(1 for i, u in raspr.items() if u == p and f(i)) for p in PRODAVCY}


bx = {
    'do': {'галочка Битрикса': sum(1 for i in vlad_do if bitrix_do[i]['bitrix_kc']),
           'клиенты Meyer': 0, 'клиенты СЦ': sum(1 for i in vlad_do if bitrix_do[i]['bitrix_klient_sc']),
           'с активными сделками КЦ/СЦ': 0},
    'po': {'галочка Битрикса': sum(1 for i in novoe if BITRIX[i]['bitrix_kc']),
           'клиенты Meyer': sum(1 for i in novoe if BITRIX[i]['bitrix_klient_meyer']),
           'клиенты СЦ': sum(1 for i in novoe if BITRIX[i]['bitrix_klient_sc']),
           'с активными сделками КЦ/СЦ': sum(1 for i in novoe if (BITRIX[i]['bitrix_v_rabote'] or 0) > 0)},
    'po_prodavcam': {'галочка': bx_schet(novoe, lambda i: BITRIX[i]['bitrix_kc']),
                     'клиенты Meyer': bx_schet(novoe, lambda i: BITRIX[i]['bitrix_klient_meyer']),
                     'клиенты СЦ': bx_schet(novoe, lambda i: BITRIX[i]['bitrix_klient_sc']),
                     'в работе КЦ/СЦ': bx_schet(novoe, lambda i: (BITRIX[i]['bitrix_v_rabote'] or 0) > 0)},
    'do_prodavcam': {'галочка': bx_schet(vlad_do, lambda i: bitrix_do[i]['bitrix_kc']),
                     'клиенты СЦ': bx_schet(vlad_do, lambda i: bitrix_do[i]['bitrix_klient_sc'])},
}
print('Битрикс до -> после: %s -> %s' % (bx['do'], bx['po']))
print('   по продавцам после: %s' % bx['po_prodavcam'])
AKT_INN = set(zagr('aktivnye_meyer_inn.json')) | set(ubrat_inn)   # все ИНН активных сделок Meyer (поле ИНН и ИНН в тексте) + по названию
akt_ostalis = sorted({i for i in novoe if aktivnaya_meyer(i)[0]} | (set(novoe) & AKT_INN))
print('компаний с активной сделкой Meyer (ИНН/ИНН в тексте) в итоговом каталоге: %d %s' % (len(akt_ostalis), akt_ostalis))
krd_do = collections.Counter(vlad[i] for i in vlad if region_do.get(i) == KRD)
krd_po = collections.Counter(novoe[i] for i in krd)
print('краснодарских: до %s, после %s' % (dict(krd_do), dict(krd_po)))
pot = collections.Counter((m['ot'], m['komu']) for m in peremeshcheniya)
print('перемещений %d: %s' % (len(peremeshcheniya), {'%s→%s' % (FIO[a], FIO[b]): n for (a, b), n in sorted(pot.items())}))
print('новые по продавцам: %s; убрано по продавцам: %s' % (dict(collections.Counter(FIO[p] for p in prodavcy.values())),
                                                         dict(collections.Counter(FIO[u['prodavec']] for u in ubrat))))
if konflikty:
    print('КОНФЛИКТЫ: %s' % konflikty)
plan = {'vremya': time.strftime('%Y%m%d-%H%M%S'), 'ubrat': ubrat, 'ostavleny_s_deystviyami': ostavleny,
        'otobrano': otobrano, 'otkaz': otkaz, 'nuzhno': NUZHNO, 'cel': CEL,
        'kompanii': kompanii, 'kontakty': [{kk: v for kk, v in x.items() if not kk.startswith('_')} for x in kontakty],
        'lyudi': lyudi, 'istochniki': istochniki, 'holding': holding, 'prodavcy': prodavcy,
        'peremeshcheniya': peremeshcheniya, 'krasnodar': {'do': dict(krd_do), 'posle': dict(krd_po), 'inn': sorted(krd)},
        'stupeni': {i: {'tier': dannye[i]['tier'], 'ball': dannye[i]['ball'], 'score': dannye[i]['score'],
                        'pochemu': dannye[i]['pochemu']} for i in SEL},
        'milp': {'zapas_stupeney': zs, 'zapas_prochih': zp, 'koridor_balla': kor, 'peremeshcheniy': len(peremeshcheniya)},
        'obshchie_nomera_novyh': obshchie_novyh, 'konflikty': konflikty, 'ne_vzyaty_nomera': zhurnal_plana,
        'tablica_do': t_do, 'tablica_posle': t_po, 'istochnik': 'файл 6', 'lpr_ne_lichnyy': LPR_NE_LICHNYY,
        'bitrix': BITRIX, 'bitrix_istochnik': ISTOCHNIK_BITRIX, 'bitrix_itog': bx, 'aktivnye_meyer_ostalis': akt_ostalis,
        'aktivnye_meyer_inn': sorted(AKT_INN),
        'bitrix_do_info': {i: bitrix_do[i]['bitrix_kc_info'] for i in bitrix_do if bitrix_do[i]['bitrix_kc_info']}}
io.open(OUT, 'w', encoding='utf-8').write(json.dumps(plan, ensure_ascii=False, indent=1))
print('план: %s' % OUT)
