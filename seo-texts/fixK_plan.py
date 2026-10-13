# -*- coding: utf-8 -*-
"""fixK (локально): план заливки базы MEYER-7 – по 120 компаний каждому из 9 продавцов (владелец 13.10: «заливай по 120
компаний всем, учитывая холдинги, города, равный приоритет»; «наиболее полную информацию из доступной»).

    python3 -E -P fixK_plan.py <папка fixK> <папка osn: db0 + kodroot> <выход plan.json>

В папке fixK: otbor.json (fixK_otbor.py: проверенный пул и ступень панели), sverka.json (Битрикс), dadata.json
(fixK_dadata.py), by.json (fixK_by_mns.py), checko/razbor.json (panel_checko_razbor.py по fixK-checko-html.zip),
fixD-holdingi.json.

ОТБОР (порядок владельца): ЛПР с ФИО и мобильным -> ЛПР с мобильным -> ЛПР с рабочим (ступень ПАНЕЛИ: rol_kontakta,
общий номер панели, формула fixF2_ball); внутри – пищевка/агро раньше прочих отраслей, затем выручка, затем сила
подтверждения сайта сборкой. Прочие отрасли с ЛПР – после пищевки с ЛПР; компании без ЛПР – последними (пищевка раньше,
по выручке; нужен хотя бы один телефон). Проверки по ходу: действующая (РФ – DaData findById + checko; РБ – реестр
МНС по УНП, нет ответа – «статус не проверен»), нет активной сделки Meyer у самой компании (ИНН, ИНН в тексте
сделки, точное название – совпадения по названию разобраны вручную ниже; холдинг/сайт клиента со сделкой – не причина,
владелец 13.10), домашние регионы (Алтайский край – 5 барнаульских, Краснодарский – Ерохин/Беляев, Воронежская –
Козлов/Тюнин), холдинг целиком одному продавцу (существующая группа панели – к её продавцу).

РАЗДАЧА – MILP (scipy/HiGHS): по 120 новых каждому из meyer1–meyer9; единица – группа холдинга/общих номеров целиком;
коридоры у 120 новых каждого: ступени 800/600/400/200, «ЛПР с мобильным», пищевка, Беларусь (выручки нет – отдельно),
пороги выручки РФ (-> медиана), тех. ЛПР, ЛПР с ФИО, Битрикс, клиенты СЦ, средний балл очереди.
"""
import collections
import io
import json
import math
import os
import re
import shutil
import sqlite3
import sys
import time

W, OSN, OUT = sys.argv[1:4]
ZDES = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ZDES)
import fixK_m7 as M  # noqa: E402

SIM = os.path.join(W, 'sim_plan')
os.makedirs(SIM, exist_ok=True)
for f in ('meyer_baza1.db', 'centro_sales_meyer1.db'):
    shutil.copy(os.path.join(OSN, 'db0', f), os.path.join(SIM, f))
os.environ['CENTRIFUGAL_DB'] = os.environ['CENTRO_DB'] = os.path.join(SIM, 'meyer_baza1.db')
os.environ['CENTRO_SALES_DB'] = os.path.join(SIM, 'centro_sales_meyer1.db')
sys.path.insert(0, os.path.join(OSN, 'kodroot'))
from app.services import centro_catalog as cat  # noqa: E402
from app.services import centro_sales as sales  # noqa: E402
import fixE1_regiony_segmenty as E1  # noqa: E402
import fixF2_ball as E2  # noqa: E402

T0 = time.time()
DATA = '13.10.2026'
NUZHNO = 120
PRODAVCY = ['meyer1', 'meyer2', 'meyer3', 'meyer4', 'meyer5', 'meyer6', 'meyer7', 'meyer8', 'meyer9']
FIO = {'meyer1': 'Пяткова', 'meyer2': 'Ерохин', 'meyer3': 'Беляев', 'meyer4': 'Волков', 'meyer5': 'Козлов',
       'meyer6': 'Тюнин', 'meyer7': 'Иванов', 'meyer8': 'Кузнецова', 'meyer9': 'Кузьмин'}
DOM = {'Алтайский край': ['meyer1', 'meyer4', 'meyer7', 'meyer8', 'meyer9'],
       'Краснодарский край': ['meyer2', 'meyer3'], 'Воронежская область': ['meyer5', 'meyer6']}
TZ = json.load(open(os.path.join(ZDES, 'okved_segment_tz.json'), encoding='utf-8'))
E1.OKVED_TZ.update(TZ)
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
IMENA = M.IMENA


def zagr(p, umolch=None):
    put = os.path.join(W, p)
    if not os.path.exists(put):
        if umolch is not None:
            return umolch
        raise SystemExit('нет файла %s' % put)
    return json.load(open(put, encoding='utf-8'))


OTB = zagr('otbor.json')
SV = zagr('sverka.json')
DD = zagr('dadata.json')
BY = zagr('by.json', {})
CH = zagr(os.path.join('checko', 'razbor.json'), {})
HOLD = zagr('fixD-holdingi.json')
pul, m, k3, dop = M.zagruzit()
sb = M.Sborka(pul, m, k3, dop)
# названия клиентов с активной сделкой Meyer – для меток контактов возвращённых из «Не вошли»
import csv  # noqa: E402
AKT_MEYER = set()        # ИНН с активной сделкой Meyer (ИНН сделки + ИНН в тексте сделки) – для проверки после заливки
for r in csv.DictReader(io.open(os.path.join(M.SCR, 'vhod-bitrix2', 'all', 'meyer_all.csv'), encoding='utf-8-sig', newline=''),
                        delimiter=';'):
    d_ = re.sub(r'\D', '', r.get('INN') or '')
    d_ = ('0' + d_) if len(d_) in (9, 11) else d_
    if r.get('АКТИВНА') == 'да':
        if d_:
            M.KLIENTY.setdefault(d_, (r.get('КОМПАНИЯ') or r.get('НАЗВАНИЕ_В_РЕКВИЗИТАХ') or '')[:80])
            AKT_MEYER.add(d_)
            if len(re.sub(r'\D', '', r.get('INN') or '')) == 9:
                AKT_MEYER.add(re.sub(r'\D', '', r.get('INN') or ''))      # УНП Беларуси как есть
        for t_ in (r.get('TITLE') or '', r.get('КОМПАНИЯ') or '', r.get('НАЗВАНИЕ_В_РЕКВИЗИТАХ') or ''):
            AKT_MEYER.update(re.findall(r'(?<!\d)(\d{12}|\d{10})(?!\d)', t_))
# владелец 13.10: список «Meyer – не покупатель» (соседняя сессия, данные): по ИНН/УНП и по домену сайта (вид «ключ»)
NEPOK_INN, NEPOK_DOM = {}, {}
for r in csv.reader(io.open(os.path.join(M.SCR, 'vhod-nepok', 'meyer-ne-pokupateli-1013-1323.csv'), encoding='utf-8-sig'), delimiter=';'):
    if r[0].startswith('ИНН или'):
        continue
    prich = ('список «Meyer – не покупатель» 13.10 (%s): %s' % (r[6], r[7]))[:250]
    if r[1] in ('ИНН', 'УНП'):
        NEPOK_INN[re.sub(r'\D', '', r[0])] = prich
    elif r[1] == 'ключ' and M.domen(r[3]):
        NEPOK_DOM[M.domen(r[3])] = prich


def nepokupatel(inn):
    if inn in NEPOK_INN:
        return NEPOK_INN[inn]
    d = M.domen(sb.komp[inn]['Сайт'])
    while d and '.' in d:
        if d in NEPOK_DOM:
            return NEPOK_DOM[d] + ' (по домену сайта %s)' % d
        d = d.split('.', 1)[1]
    return ''


print('данные прочитаны за %.0f с: кандидатов %d, dadata %d, РБ %d, checko %d' % (time.time() - T0, len(OTB['kandidaty']), len(DD),
                                                                                    len(BY), len(CH)))

k = sqlite3.connect(os.path.join(SIM, 'meyer_baza1.db'))
k.row_factory = sqlite3.Row
s_ = sqlite3.connect(os.path.join(SIM, 'centro_sales_meyer1.db'))
panel = {r['inn']: dict(r) for r in k.execute('SELECT * FROM company')}
arhiv = {r[0] for r in k.execute('SELECT inn FROM arhiv_company')}
VOR16 = set(OTB['vor16'])
vlad = dict(s_.execute('SELECT inn, username FROM company_assignment').fetchall())
assert set(vlad) == set(panel) and len(panel) == 600, (len(vlad), len(panel))


def region_oficialnyy(inn, c):
    """-> (регион, откуда)."""
    if len(inn) == 9:
        a = (BY.get(inn) or {}).get('vpadres') or ''
        m_ = re.search(r'(Брестская|Витебская|Гомельская|Гродненская|Минская|Могил[её]вская) область', a)
        if m_:
            return 'Беларусь, %s область' % m_.group(1).replace('Могилевская', 'Могилёвская'), 'адрес в реестре МНС РБ'
        if re.search(r'г\. ?Минск', a):
            return 'Беларусь, Минск', 'адрес в реестре МНС РБ'
        return 'Беларусь', 'сборка MEYER-7'
    z = CH.get(inn) or {}
    sub, _ = E1.subekt_adresa(z.get('adres')) if z.get('adres') and not z.get('oshibka') else ('', '')
    if sub:
        return sub, 'юрадрес checko.ru'
    rd = (DD.get(inn) or {}).get('region')
    if rd and E1.region_norm(rd) in E1.OFICIALNYE:
        return E1.region_norm(rd), 'адрес ЕГРЮЛ (DaData)'
    rg = E1.region_norm(M.s(c['Регион']))
    return rg, 'сборка MEYER-7'


def status_proverka(inn):
    """-> (годна, текст статуса для status_egrul, причина отказа)."""
    if len(inn) == 9:
        z = BY.get(inn) or {}
        st = z.get('vkods')
        if not st:
            return True, 'Беларусь: статус не проверен (реестр МНС РБ не ответил)', ''
        if st == 'Действующий':
            return True, 'Беларусь: действующий (реестр МНС РБ, %s)' % DATA, ''
        return False, '', 'Беларусь: «%s» по реестру МНС РБ' % st
    d = DD.get(inn) or {}
    st = d.get('status')
    if not st:
        return False, '', 'нет в ЕГРЮЛ по DaData'
    if st not in ('ACTIVE', 'REORGANIZING'):
        return False, '', 'ЕГРЮЛ (DaData): %s' % st
    z = CH.get(inn) or {}
    if z and not z.get('oshibka') and z.get('status'):
        n = E1.nedeystvuyushchaya(z['status'])
        if n:
            return False, '', 'checko: ' + n
        return True, z['status'] + (('; правопреемник %s' % z['pravopreemnik']) if z.get('pravopreemnik') else ''), ''
    return True, {'ACTIVE': 'Действующая компания', 'REORGANIZING': 'Действующая, в процессе реорганизации'}[st] + ' (ЕГРЮЛ по DaData)', ''


def dom_region(reg):
    return reg if reg in DOM else ''


# ====================================================================== 1. ОТБОР
K = OTB['kandidaty']


def vyr_dlya(inn):
    z = CH.get(inn) or {}
    if z.get('vyruchka') is not None and not z.get('oshibka'):
        return float(z['vyruchka'])
    return K[inn]['vyr']


def poryadok(z):
    lpr = z['tier'] >= 2
    grp = 0 if (lpr and z['eda']) else 1 if lpr else 2 if z['eda'] else 3
    return (grp, -z['tier'] if lpr else 0, -(vyr_dlya(z['inn']) or 0), -z['sila_sayta'], z['inn'])


ochered = sorted((z for z in K.values() if z['tier'] >= 2 or z['n_tel'] > 0), key=poryadok)
bez_tel = sum(1 for z in K.values() if z['tier'] == 1 and z['n_tel'] == 0)
EMK = {'Алтайский край': 600, 'Краснодарский край': 240, 'Воронежская область': 240}
pomet = {}


def otobrat(isklyuchit):
    """-> (vybor, otkaz). isklyuchit: ИНН -> причина (конфликт «холдинг – домашний регион»)."""
    otkaz = collections.OrderedDict()
    vybor = []
    reg_sch = collections.Counter()
    for z in ochered:
        if len(vybor) >= NUZHNO * len(PRODAVCY):
            break
        inn = z['inn']
        c = sb.komp[inn]
        pr = []
        if inn in panel:
            pr.append('уже в панели')
        if inn in arhiv and inn not in VOR16:
            pr.append('в архиве панели')
        if inn in IMENA and IMENA[inn][0]:
            pr.append('активная сделка Meyer по точному названию (проверено вручную): ' + IMENA[inn][1])
        v_ = vyr_dlya(inn)
        if v_ is not None and v_ < 3e7:
            pr.append('выручка %.1f млн по checko – меньше 30 млн (владелец 13.10)' % (v_ / 1e6))
        ok, st_tekst, prich = status_proverka(inn)
        if not ok:
            pr.append('недействующая: ' + prich)
        reg, reg_ist = region_oficialnyy(inn, c)
        if reg in EMK and reg_sch[reg] >= EMK[reg]:
            pr.append('домашний регион %s заполнен (%d)' % (reg, EMK[reg]))
        if inn in isklyuchit:
            pr.append(isklyuchit[inn])
        np_ = nepokupatel(inn)
        if np_:
            pr.append(np_)
        if pr:
            otkaz[inn] = pr
            continue
        reg_sch[reg] += 1
        pomet[inn] = {'status': st_tekst, 'region': reg, 'region_istochnik': reg_ist}
        vybor.append(inn)
    return vybor, otkaz


# возможные сделки по названию из otbor (там – отказ «не беру без проверки»): тёзки по ручному разбору – вернуть в очередь
vernut = [i for i, (plohaya, _) in IMENA.items() if not plohaya]
print('тёзки сделок по названию (вручную – не та компания): %d – в очередь возвращаются, если проходят: %s' % (
    len(vernut), [i for i in vernut if i in K]))


# ====================================================================== 2. СТРОКИ КАТАЛОГА
def direktor(z):        # = panel_checko_zalit.direktor
    fio = (z.get('ruk_fio') or '').strip()
    if not fio:
        return ''
    dolzh = (z.get('ruk_dolzhnost') or '').strip()
    if dolzh and not dolzh.isupper():
        dolzh = dolzh[0].lower() + dolzh[1:]
    hv = ', '.join(x for x in (dolzh, ('с ' + z['ruk_s']) if z.get('ruk_s') else '') if x)
    return '%s (%s)' % (fio, hv) if hv else fio


def otrasl(kod, seg_sborki):
    kod = (kod or '').strip()
    l_ = max((n for n, _ in OTRASLI if kod.startswith(n)), key=len, default='')
    o = dict(OTRASLI)[l_] if l_ else 'прочее'
    if o in ('прочее', 'оптовая торговля', 'розничная торговля') and seg_sborki:
        b = re.sub(r'\s*\((?:[^()]*)\)\s*$', '', seg_sborki)
        b = re.sub(r'\s*—\s*ИНН не определён\s*$', '', b).strip()
        if b:
            return b
    return o


def bitrix_polya(inn):
    x = SV['kandidaty'].get(inn) or {}
    p = {kk: x.get(kk) for kk in ('bitrix_kc', 'bitrix_kc_info', 'bitrix_sdelok', 'bitrix_klient_sc', 'bitrix_klient_meyer',
                                  'bitrix_v_rabote', 'bitrix_poslednyaya')}
    for kk in ('bitrix_kc', 'bitrix_sdelok', 'bitrix_klient_sc', 'bitrix_klient_meyer', 'bitrix_v_rabote'):
        p[kk] = int(p[kk] or 0)
    p['bitrix_istochnik'] = 'выгрузка Битрикса 09.10'
    return p


PASPORT = [('pasport_syrye', 'Паспорт: сырьё'), ('moshchnosti', 'Паспорт: мощности'),
           ('pasport_kachestvo', 'Паспорт: контроль качества'), ('pasport_oborudovanie', 'Паспорт: оборудование и линии'),
           ('pasport_upakovka', 'Паспорт: упаковка и фасовка'), ('pasport_eksport', 'Паспорт: экспорт'),
           ('pasport_masshtab', 'Паспорт: масштаб')]
NOVYE_KOLONKI_COMPANY = [('segment_meyer7', 'TEXT'), ('pasport_syrye', 'TEXT'), ('pasport_kachestvo', 'TEXT'),
                         ('pasport_oborudovanie', 'TEXT'), ('pasport_upakovka', 'TEXT'), ('pasport_eksport', 'TEXT'),
                         ('pasport_masshtab', 'TEXT'), ('reviziya_profil', 'TEXT'), ('gruppa_meyer7', 'TEXT'),
                         ('naydena_po_zaprosu', 'TEXT'), ('baza_obzvona_direktor', 'TEXT'), ('baza_obzvona_telefony', 'TEXT'),
                         ('baza_obzvona_pochty', 'TEXT'), ('teh_sluzhby_baza', 'TEXT'), ('inn_nayden_po_saytu', 'TEXT'),
                         ('segment_kak', 'TEXT'), ('vyruchka_istochnik', 'TEXT'), ('strana', 'TEXT'), ('lpr_sborki', 'TEXT'),
                         ('pismo_sborki', 'TEXT'), ('kontaktov_sborki', 'TEXT'), ('poyasnenie_agenta', 'TEXT'),
                         ('spornyy_sayt', 'TEXT'), ('v_nashey_baze', 'TEXT'), ('istochniki', 'TEXT'), ('istochnikov', 'INTEGER'),
                         ('status_proveren', 'TEXT')]


def stroka_kompanii(inn):
    c = sb.komp[inn]
    pm = pomet[inn]
    z = CH.get(inn) or {}
    if z.get('oshibka'):
        z = {}
    d = DD.get(inn) or {}
    rb = len(inn) == 9
    vyr_sb = M.chislo(c['Выручка, руб'])
    row = {'inn': inn, 'predpriyatie': M.s(c['Название']), 'region': pm['region'], 'region_ishodnyy': M.s(c['Регион']) or None,
           'region_istochnik': pm['region_istochnik'], 'strana': M.s(c['Страна']) or ('Беларусь' if rb else 'Россия'),
           'sayt': M.s(c['Сайт']), 'okved': M.s(c['Основной ОКВЭД']) or (d.get('okved') or ''),
           'status_egrul': pm['status'], 'status_proveren': ('реестр МНС РБ' if rb else 'DaData findById' + (' + checko.ru' if z else '')) + ' ' + DATA,
           'bazy': M.BAZA, 'bazy_opisanie': M.BAZA_OPIS, 'v_baze_obzvona': None, 'has_signal': 0, 'n_signals': 0, 'n_facts': 0}
    if rb:
        row['status_proveren'] = 'реестр МНС РБ %s' % DATA if (BY.get(inn) or {}).get('vkods') else 'не проверен'
        b = BY.get(inn) or {}
        row['adres'] = b.get('vpadres') or ''
        row['chas_poyas'], row['chas_poyas_kak'] = 3, 'по стране: Беларусь (UTC+3)'
    else:
        row['chas_poyas'], row['chas_poyas_kak'] = E1.poyas(pm['region'])
        row['adres'] = z.get('adres') or d.get('adres') or ''
        row['direktor'] = direktor(z) if z.get('ruk_fio') else (
            '%s (%s, по ЕГРЮЛ через DaData)' % (d['ruk'], (d.get('ruk_dolzhnost') or '').lower()) if d.get('ruk') else '')
        if z.get('ssch') is not None:
            row['ssch'], row['ssch_god'] = z['ssch'], z.get('ssch_god') or ''
    # деньги: checko за последний год; иначе – выручка сборки
    if z.get('fin_god') and z.get('vyruchka') is not None:
        row['vyruchka_rub'], row['fin_god'], row['chistaya_pribyl'] = float(z['vyruchka']), z['fin_god'], z.get('pribyl')
        row['vyruchka_istochnik'] = 'checko.ru (данные ФНС за %s год), %s' % (z['fin_god'], DATA)
        if vyr_sb is not None and abs(vyr_sb - float(z['vyruchka'])) > max(1.0, 0.005 * abs(vyr_sb)):
            row['vyruchka_ishodnaya'] = vyr_sb
    elif vyr_sb is not None:
        row['vyruchka_rub'] = vyr_sb
        row['vyruchka_istochnik'] = 'сборка MEYER-7: ' + (M.s(c['Откуда выручка']) or 'источник не указан')
        if z.get('fin_god'):
            row['fin_god'], row['chistaya_pribyl'] = z['fin_god'], z.get('pribyl')
    else:
        row['vyruchka_istochnik'] = 'нет данных (Беларусь: отчётности в открытом доступе нет)' if rb else 'нет данных'
    pochty_checko = list(z.get('pochty') or [])
    if not rb:
        row['istochnik_rekvizitov'] = ('checko.ru %s' % DATA) if z else ('ЕГРЮЛ (DaData) %s' % DATA)
    else:
        row['istochnik_rekvizitov'] = 'реестр плательщиков МНС РБ %s' % DATA if (BY.get(inn) or {}).get('vkods') else ''
    # ОКВЭД, сегмент шкалы панели, сегмент сборки, отрасль, попадание
    osn = row['okved']
    dopk = [x.strip() for x in M.s(c['Доп. ОКВЭД']).split(',') if x.strip()]
    row['okvedy_vse'] = ' | '.join([osn] + [x for x in dopk if x != osn]) if osn else ' | '.join(dopk)
    seg = E1.segs(E1.segment_tz(osn))
    row['segment'] = row['segment_osn'] = ' | '.join(seg)
    iz_dop = E1.poryadok([s_ for k_ in dopk for s_ in E1.segs(E1.segment_tz(k_)) if s_ not in seg])
    row['segment_dop'] = ' | '.join(iz_dop)
    row['segment_meyer7'] = M.s(c['Сегмент'])
    row['segment_kak'] = M.s(c['Как определён сегмент'])
    row['popadanie'] = 'основной ОКВЭД' if (seg or 'основн' in row['segment_kak']) else 'только доп. ОКВЭД'
    row['otrasl'] = otrasl(osn, row['segment_meyer7'])
    row['pometka_ocheredi'] = ''
    # описание, продукция, паспорт
    poy = sb.poyasneniya.get(inn) or {}
    row['opisanie'] = M.s(c['Описание (по сайту)']) or M.s(poy.get('Пояснение агента'))[:1500]
    row['produkciya'] = M.s(c['Продукция'])
    for kol, nazv in PASPORT:
        row[kol] = M.s(c[nazv])
    row['poyasnenie_agenta'] = ' · '.join(x for x in (M.s(poy.get('Пояснение агента')), ('доказательство: ' + M.s(poy.get('Доказательство')))
                                                    if M.s(poy.get('Доказательство')) else '') if x)[:3000] or None
    sp = sb.spornye.get(inn) or {}
    row['spornyy_sayt'] = ('%s: %s' % (M.s(sp.get('Кто сомневается')), M.s(sp.get('Почему'))))[:1500] if sp else None
    # сайт
    vid_s, sila = M.sayt_prinyat(c['Сайт: чей'])
    row['proverka_sayta'] = vid_s
    row['sayt_chey'] = ('Проверка сборки MEYER-7 %s: %s' % (DATA, M.s(c['Сайт: чей'])))[:1500]
    row['inn_nayden_po_saytu'] = M.s(c['ИНН найден по сайту: юрлицо']) or None
    # прочее сборки
    row['reviziya_profil'] = M.s(c['Ревизия: профиль']) or None
    row['gruppa_meyer7'] = M.s(c['Группа']) or None
    row['otkuda_kompaniya'] = M.s(c['Откуда компания'])
    row['naydena_po_zaprosu'] = M.s(c['Найдена по запросу']) or None
    row['v_fajlah_meyer'] = M.s(c['Есть в файлах Meyer 1–6'])
    row['baza_obzvona_direktor'] = M.s(c['База обзвона: директор']) or None
    row['baza_obzvona_telefony'] = M.s(c['База обзвона: телефоны']) or None
    row['baza_obzvona_pochty'] = M.s(c['База обзвона: почты']) or None
    row['teh_sluzhby_baza'] = M.s(c['Тех. службы (наша база)']) or None
    row['v_nashey_baze'] = ', '.join(x for x in (('есть в нашей базе' if M.s(c['Есть в нашей базе']) == 'да' else ''),
                                                 ('в реестре (наши базы, регион пилота)' if M.s(c['В реестре (наши базы, регион пилота)']) == 'да' else '')) if x) or None
    row['lpr_sborki'] = ' · '.join(x for x in (M.s(c['ЛПР: ФИО']), M.s(c['ЛПР: должность']), M.s(c['ЛПР: роль']),
                                               M.s(c['ЛПР: телефон']), M.s(c['ЛПР: e-mail'])) if x) or None
    row['pismo_sborki'] = ' · '.join(x for x in (M.s(c['Письмо: e-mail']), M.s(c['Письмо: кому (ФИО)']), M.s(c['Письмо: должность']),
                                                 ('ступень ' + M.s(c['Письмо: ступень лесенки'])) if M.s(c['Письмо: ступень лесенки']) else '') if x) or None
    row['kontaktov_sborki'] = ('номеров %s, почт %s, из них ЛПР %s, мобильных %s' % tuple(
        M.s(c[x]) or '0' for x in ('Номеров', 'Почт', 'Из них ЛПР', 'Мобильных'))) if not c.get('_vozvrat') else None
    row['ssylki_na_istochniki'] = ' | '.join(x.strip() for x in M.s(c['Где найдены контакты']).split('\n') if x.strip())[:4000]
    hold = M.s(c['Холдинг (агент)'])
    row['holding'] = (re.sub(r'\s*\(не подтверждено[^)]*\)', '', hold) + ' (по данным составителя файла)') if hold else ''
    row['holding_gruppa'] = ''
    row.update(bitrix_polya(inn))
    return row, pochty_checko


KESH = {}
stat_k = collections.Counter()


def stroki(inn):
    """Строки каталога одной компании (кэш): company, номера, люди, источники."""
    if inn in KESH:
        return KESH[inn]
    row, pch = stroka_kompanii(inn)
    kont, lyud, pochty, zh = M.kontakty_kompanii(sb, inn, cat)
    # почты: checko (как panel_checko_zalit) + сборка с пометкой (как fixJ) – в company.pochta
    vse, est = [], set()
    for e, prim in pch:
        if e.lower() not in est:
            est.add(e.lower())
            vse.append('%s (%s)' % (e, ('checko: ' + prim) if prim else 'checko'))
    for e, pom, lpr in pochty:
        if e.lower() not in est:
            est.add(e.lower())
            vse.append('%s (%s)' % (e, pom))
    row['pochta'] = ', '.join(vse)[:6000]
    ist_ = []
    z = CH.get(inn) or {}
    if z.get('ogrn') and not z.get('oshibka'):
        ist_.append({'inn': inn, 'field_name': 'Реквизиты, руководитель, финансы (checko)', 'source': 'checko.ru %s' % DATA,
                     'source_url': 'https://checko.ru/company/' + z['ogrn']})
    if len(inn) in (10, 12):
        d = DD.get(inn) or {}
        ist_.append({'inn': inn, 'field_name': 'Статус ЕГРЮЛ (DaData)', 'source': 'DaData findById %s: %s%s' % (
            DATA, d.get('status'), (', ОГРН %s' % d['ogrn']) if d.get('ogrn') else ''), 'source_url': ''})
    else:
        b_ = BY.get(inn) or {}
        ist_.append({'inn': inn, 'field_name': 'Статус плательщика (МНС Беларуси)',
                     'source': ('реестр МНС РБ %s: %s, рег. %s' % (DATA, b_.get('vkods'), b_.get('dreg'))) if b_.get('vkods') else
                     'реестр МНС РБ %s: ответа нет – статус не проверен' % DATA, 'source_url': 'https://grp.nalog.gov.by/grp/'})
    ist_.append({'inn': inn, 'field_name': 'Сайт и контакты (сборка MEYER-7)', 'source': row['sayt_chey'][:500],
                 'source_url': row['sayt'] if row['sayt'].startswith('http') else ''})
    for x in kont:
        if x.get('_lpr') and x.get('source_url'):
            ist_.append({'inn': inn, 'field_name': 'ЛПР: %s' % (x.get('position') or x['_rol']),
                         'source': 'сайт компании (MEYER-7 13.10)', 'source_url': x['source_url'].split(' ; ')[0]})
    ist = ['сборка MEYER-7 13.10']
    if z.get('ogrn'):
        ist.append('checko.ru')
    if DD.get(inn):
        ist.append('ЕГРЮЛ (DaData)')
    if (BY.get(inn) or {}).get('vkods'):
        ist.append('реестр МНС РБ')
    if row.get('bitrix_kc'):
        ist.append('Битрикс 09.10')
    row['istochniki'], row['istochnikov'] = ' | '.join(ist), len(ist)
    KESH[inn] = {'row': row, 'kont': kont, 'lyud': lyud, 'ist': ist_, 'zh': zh}
    return KESH[inn]


# ---------------------------------------------------------------- группы: холдинги, общие номера, связи с панелью
def norm_h(h):
    h = M.s(h).lower()
    h = re.sub(r'\(.*?\)', ' ', h)
    h = re.sub(r'\b(ооо|ао|пао|зао|оао|гк|группа компаний|холдинг|агрохолдинг)\b', ' ', h)
    h = re.sub(r'[«»"\'“”„.,]', ' ', h)
    return ' '.join(h.split())


NOM_PANELI = collections.defaultdict(set)
for r in k.execute("SELECT inn, value FROM contact WHERE kind='phone' AND TRIM(COALESCE(chuzhoy_istochnik,''))=''"):
    kk = cat._phone_key(r['value'])
    if kk:
        NOM_PANELI[kk].add(r['inn'])
HC = collections.defaultdict(list)
for r in k.execute("SELECT gruppa, inn FROM holding_chlen WHERE gruppa NOT LIKE 'snyato%'"):
    HC[r['gruppa']].append(r['inn'])


def gruppy(vybor):
    rod = {}

    def koren(a):
        rod.setdefault(a, a)
        while rod[a] != a:
            rod[a] = rod[rod[a]]
            a = rod[a]
        return a

    def soed(a, b):
        rod[koren(a)] = koren(b)
    VYB = set(vybor)
    svyazi = collections.defaultdict(set)
    for g in sb.gruppy:                                   # (а) общий сайт – лист «Группы»
        chl = [i for i in g['inns'] if i in VYB or i in panel]
        if len(chl) > 1 and any(i in VYB for i in chl):
            for i in chl:
                svyazi[i].add('общий сайт группы %s (лист «Группы» MEYER-7)' % g['sayt'])
            for i in chl[1:]:
                soed(chl[0], i)
    po_h = collections.defaultdict(list)                  # (б) холдинг агента – только между новыми
    for i in vybor:
        h = norm_h(sb.komp[i]['Холдинг (агент)'])
        if h:
            po_h[h].append(i)
    for h, inns in po_h.items():
        if len(inns) > 1:
            for i in inns:
                svyazi[i].add('холдинг «%s» по данным составителя файла (не подтверждено)' % h)
            for i in inns[1:]:
                soed(inns[0], i)
    po_nom = collections.defaultdict(set)                 # (в) общие номера (без помеченных чужими)
    for kk, inns in NOM_PANELI.items():
        po_nom[kk] |= inns
    for i in vybor:
        for x in KESH[i]['kont']:
            if not M.s(x.get('chuzhoy_istochnik')):
                kk = cat._phone_key(x['value'])
                if kk:
                    po_nom[kk].add(i)
    for kk, inns in po_nom.items():
        if len(inns) > 1 and inns & VYB:
            inns = sorted(inns)
            for i in inns:
                svyazi[i].add('общий номер …%s с %s' % (kk[-4:], ', '.join(x for x in inns if x != i)[:120]))
            for i in inns[1:]:
                soed(inns[0], i)
    for g, chl in HC.items():                             # (г) группы панели
        if set(chl) & VYB:
            for i in chl:
                svyazi[i].add('группа панели %s' % g)
            for i in chl[1:]:
                soed(chl[0], i)
    for i in vybor:
        g = HOLD['inn_gruppa'].get(i)
        if g:
            for j, gg in HOLD['inn_gruppa'].items():
                if gg == g and j in panel:
                    svyazi[i].add('группа панели %s (fixD)' % g)
                    soed(i, j)
    komp = collections.defaultdict(list)
    for i in vybor:
        komp[koren(i)].append(i)
    edinicy = {}
    for kor, chl in komp.items():
        edinicy['u-' + min(chl)] = {'novye': sorted(chl), 'panel': sorted({j for j in rod if koren(j) == kor and j in panel})}
    # допустимые продавцы и конфликты «холдинг – домашний регион»: владелец разрешает только своему городу,
    # холдинг – целиком одному; если вместе нельзя – новая компания-нарушитель не берётся (замена следующей по очереди)
    dop_, isk = {}, {}
    for u, e in edinicy.items():
        mozhno = set(PRODAVCY)
        po_reg = collections.defaultdict(list)
        for i in e['novye']:
            if pomet[i]['region'] in DOM:
                po_reg[pomet[i]['region']].append(i)
        for reg in po_reg:
            mozhno &= set(DOM[reg])
        prod_panel = sorted({vlad[j] for j in e['panel']})
        if len(prod_panel) > 1:
            for i in e['novye']:
                isk[i] = 'группа связана с компаниями панели у разных продавцов (%s) – не беру, чтобы не рвать холдинг' % prod_panel
            continue
        if prod_panel:
            p0 = prod_panel[0]
            if p0 in mozhno:
                mozhno = {p0}
            else:
                for i in e['novye']:
                    if pomet[i]['region'] in DOM and p0 not in DOM[pomet[i]['region']]:
                        isk[i] = ('холдинг/общий номер с компанией панели у %s, а регион %s – только %s: правила '
                                  'холдинга и городов вместе не выполнить – не беру' % (FIO[p0], pomet[i]['region'],
                                                                                        ', '.join(FIO[p] for p in DOM[pomet[i]['region']])))
                if not any(i in isk for i in e['novye']):
                    for i in e['novye']:
                        isk[i] = 'холдинг с компанией панели у %s – не беру (правило городов)' % FIO[p0]
                continue
        if not mozhno:
            # разные домашние регионы в одной группе: оставляется регион с бОльшим числом членов, прочие не берутся
            glav = max(po_reg, key=lambda r_: (len(po_reg[r_]), -min(ochered_mesto[i] for i in po_reg[r_])))
            for reg, chl in po_reg.items():
                if reg != glav:
                    for i in chl:
                        isk[i] = ('в одной группе с компаниями региона %s (только %s), а регион %s – только %s: '
                                  'не беру' % (glav, ', '.join(FIO[p] for p in DOM[glav]), reg, ', '.join(FIO[p] for p in DOM[reg])))
            continue
        dop_[u] = sorted(mozhno)
    return edinicy, svyazi, dop_, isk


ochered_mesto = {z['inn']: n for n, z in enumerate(ochered)}
isklyuchit = {}
for popytka in range(10):
    vybor, otkaz = otobrat(isklyuchit)
    for inn in vybor:
        stroki(inn)
    edinicy, svyazi, dop_, isk = gruppy(vybor)
    print('проход %d: взято %d, единиц %d, конфликтов «холдинг – город»: %d' % (popytka + 1, len(vybor), len(edinicy), len(isk)))
    if not isk:
        break
    isklyuchit.update(isk)
else:
    raise SystemExit('конфликты групп не сошлись')
print('отбор: просмотрено %d (до места %d из %d в очереди), взято %d; отказ на проверках %d: %s' % (
    len(vybor) + len(otkaz), ochered_mesto[vybor[-1]] + 1, len(ochered), len(vybor), len(otkaz),
    dict(collections.Counter(v[0].split(':')[0][:60] for v in otkaz.values()))))
konflikty = [(i, isklyuchit[i]) for i in isklyuchit]
for i, pr in konflikty:
    print('   конфликт: %s %s – %s' % (i, K[i]['nazvanie'][:40], pr[:160]))
kompanii = {i: KESH[i]['row'] for i in vybor}
kontakty = [x for i in vybor for x in KESH[i]['kont']]
lyudi = [x for i in vybor for x in KESH[i]['lyud']]
istochniki = [x for i in vybor for x in KESH[i]['ist']]
for i in vybor:
    stat_k.update(KESH[i]['zh'])
region = {i: kompanii[i]['region'] for i in vybor}
print('строки: компаний %d, номеров %d, людей %d, источников %d; контакты: %s' % (
    len(kompanii), len(kontakty), len(lyudi), len(istochniki), dict(stat_k)))
print('единиц раздачи %d (групп из 2+ новых %d; связаны с компаниями панели %d)' % (
    len(edinicy), sum(1 for e in edinicy.values() if len(e['novye']) > 1), sum(1 for e in edinicy.values() if e['panel'])))

# ====================================================================== 3. ВСТАВКА В КОПИЮ КАТАЛОГА, СТУПЕНЬ И БАЛЛ
kol_c = {r[1] for r in k.execute('PRAGMA table_info(company)')}
for kol, tip in NOVYE_KOLONKI_COMPANY:
    if kol not in kol_c:
        k.execute('ALTER TABLE company ADD COLUMN %s %s' % (kol, tip))
kol_c = {r[1] for r in k.execute('PRAGMA table_info(company)')}
kol_k = {r[1] for r in k.execute('PRAGMA table_info(contact)')}
kol_p = {r[1] for r in k.execute('PRAGMA table_info(person)')}
lishnie = sorted({kk for r in kompanii.values() for kk in r} - kol_c)
assert not lishnie, 'колонок нет в каталоге: %s' % lishnie
for r in kompanii.values():
    k.execute('INSERT INTO company (%s) VALUES (%s)' % (','.join('"%s"' % x for x in r), ','.join('?' * len(r))), list(r.values()))
for x in kontakty:
    rr = {kk: v for kk, v in x.items() if kk in kol_k and not kk.startswith('_')}
    k.execute('INSERT INTO contact (%s) VALUES (%s)' % (','.join(rr), ','.join('?' * len(rr))), list(rr.values()))
for x in lyudi:
    rr = {kk: v for kk, v in x.items() if kk in kol_p}
    k.execute('INSERT INTO person (%s) VALUES (%s)' % (','.join(rr), ','.join('?' * len(rr))), list(rr.values()))
k.commit()
_kesh_sh = {}
_orig_sh = cat._shared_phone_keys


def _sh(conn):          # общий номер панели считается один раз (каталог в цикле не меняется)
    if 'k' not in _kesh_sh:
        _kesh_sh['k'] = _orig_sh(conn)
    return _kesh_sh['k']


cat._shared_phone_keys = _sh
dannye = {}
flagi_novyh = {}
for inn in vybor:
    c = dict(k.execute('SELECT * FROM company WHERE inn=?', (inn,)).fetchone())
    items = cat.contacts(inn)
    f = M.flagi(cat, items)
    f['search_blob'] = M.search_blob(cat, inn, c, items, f['lpr_kratko'])
    c.update(f)
    d = E2.razbor_kompanii(c, items, cat, sales)
    f['moy_prioritet'], f['prioritet_pochemu'] = d['ball'], d['pochemu']
    f['kachestvo_nomera'] = {4: 'ЛПР мобильный', 3: 'ЛПР мобильный', 2: 'ЛПР рабочий / с добавочным', 1: 'ЛПР не найден'}[d['tier']]
    flagi_novyh[inn] = f
    d['eda'] = int(bool(K[inn]['eda']))
    d['rb'] = int(len(inn) == 9)
    d['vozvrat'] = int(bool(K[inn].get('vozvrat')))
    dannye[inn] = d
cat._shared_phone_keys = _orig_sh
for inn, f in flagi_novyh.items():
    k.execute('UPDATE company SET %s WHERE inn=?' % ', '.join('"%s"=?' % x for x in f), list(f.values()) + [inn])
k.commit()
for inn in vybor:
    kompanii[inn].update(flagi_novyh[inn])
sch_t = collections.Counter((dannye[i]['tier'], K[i]['tier']) for i in vybor)
print('ступень в копии каталога (итоговый состав) против предварительной: %s' % sorted(sch_t.items()))

# ====================================================================== 5. РАЗДАЧА (MILP)
import numpy as np  # noqa: E402
from scipy.optimize import Bounds, LinearConstraint, milp  # noqa: E402

U = sorted(edinicy)
idx = {}
for u in U:
    for p in dop_[u]:
        idx[(u, p)] = len(idx)
nx = len(idx)
rf_vyr = sorted(dannye[i]['vyr'] for i in vybor if not dannye[i]['rb'] and dannye[i]['vyr'])
porogi = [rf_vyr[int(len(rf_vyr) * q)] for q in (0.2, 0.35, 0.45, 0.5, 0.55, 0.65, 0.8)]
metriki = [('t4', lambda r: int(r['tier'] == 4)), ('t3', lambda r: int(r['tier'] == 3)), ('t2', lambda r: int(r['tier'] == 2)),
           ('t1', lambda r: int(r['tier'] == 1)), ('lpr_mob_vse', lambda r: int(r['tier'] in (3, 4))),
           ('eda', lambda r: r['eda']), ('rb', lambda r: r['rb']), ('tech', lambda r: r['tech']), ('lpr_fio', lambda r: r['lpr_fio']),
           ('bitrix', lambda r: r['bitrix']), ('klient_sc', lambda r: r['klient_sc']),
           ('rf_bez_vyr', lambda r: int(not r['rb'] and not r['vyr']))]
for n_t, t in enumerate(porogi):
    metriki.append(('vyr_nizhe%d' % n_t, (lambda tt: (lambda r: int(not r['rb'] and bool(r['vyr']) and r['vyr'] < tt)))(t)))
STUPENI = {'t4', 't3', 't2', 't1', 'lpr_mob_vse'}
N_ = len(PRODAVCY)


def polosa(tot, w):
    if w <= 1:
        return tot // N_, -(-tot // N_)
    lo = -(-tot // N_) - (w // 2)
    return lo, lo + w


def reshit(zs, zp, kor, vremya=240):
    A, lo, hi = [], [], []
    for u in U:
        row = np.zeros(nx)
        for p in dop_[u]:
            row[idx[(u, p)]] = 1
        A.append(row); lo.append(1); hi.append(1)
    for p in PRODAVCY:
        row = np.zeros(nx)
        for u in U:
            if (u, p) in idx:
                row[idx[(u, p)]] = len(edinicy[u]['novye'])
        A.append(row); lo.append(NUZHNO); hi.append(NUZHNO)
    for kl, f in metriki:
        tot = sum(f(dannye[i]) for i in vybor)
        a, b = polosa(tot, zs if kl in STUPENI else zp)
        for p in PRODAVCY:
            row = np.zeros(nx)
            for u in U:
                if (u, p) in idx:
                    row[idx[(u, p)]] = sum(f(dannye[i]) for i in edinicy[u]['novye'])
            A.append(row); lo.append(a); hi.append(b)
    sr = sum(dannye[i]['score'] for i in vybor) / len(vybor)
    for p in PRODAVCY:
        row = np.zeros(nx)
        for u in U:
            if (u, p) in idx:
                row[idx[(u, p)]] = sum(dannye[i]['score'] for i in edinicy[u]['novye'])
        A.append(row); lo.append((sr - kor) * NUZHNO); hi.append((sr + kor) * NUZHNO)
    return milp(np.zeros(nx), constraints=LinearConstraint(np.array(A), lo, hi), integrality=np.ones(nx),
                bounds=Bounds(0, 1), options={'time_limit': vremya})


VARIANTY = [(1, 1, 3), (1, 2, 4), (2, 2, 5), (2, 3, 8), (2, 4, 12), (3, 5, 20)]
res = None
for zs, zp, kor in VARIANTY:
    r_ = reshit(zs, zp, kor)
    ok_ = r_.x is not None and r_.status in (0, 1)
    print('MILP: ступени ±%d, прочие ±%d, средний балл ±%d: %s' % (zs, zp, kor, r_.message[:50]))
    if ok_:
        res, VAR = r_, (zs, zp, kor)
        break
if res is None:
    raise SystemExit('раскладка не найдена')
prodavec = {}
for (u, p), j in idx.items():
    if res.x[j] > 0.5:
        for i in edinicy[u]['novye']:
            prodavec[i] = p
assert len(prodavec) == len(vybor)


def tablica(raspr):
    po = {p: [dannye[i] for i in vybor if raspr[i] == p] for p in PRODAVCY}
    st = ['%-34s %s %s' % ('', ' '.join('%9s' % FIO[p][:9] for p in PRODAVCY), ' разница')]
    chisla = {}

    def stroka(nazv, v, fmt='%9d'):
        st.append('%-34s %s %8s' % (nazv[:34], ' '.join(fmt % x for x in v), (fmt % (max(v) - min(v))).strip()))
    stroka('новых компаний', [len(po[p]) for p in PRODAVCY])
    for kl, nazv in (('t4', 'ЛПР ФИО+мобильный (800)'), ('t3', 'ЛПР мобильный (600)'), ('t2', 'ЛПР рабочий (400)'),
                     ('t1', 'без ЛПР (200)'), ('lpr_mob_vse', 'ЛПР с мобильным, всего'), ('eda', 'пищевка/агро'),
                     ('rb', 'Беларусь'), ('tech', 'тех. ЛПР'), ('lpr_fio', 'ЛПР с ФИО'), ('bitrix', 'есть в Битриксе'),
                     ('klient_sc', 'клиенты СЦ'), ('vozvrat', 'из «Не вошли» (сайт клиента)')):
        f = dict(metriki).get(kl) or (lambda r, kl=kl: r[kl])
        v = [sum(f(r) for r in po[p]) for p in PRODAVCY]
        chisla[kl] = v
        stroka(nazv, v)
    med = [E2.mediana([r['vyr'] for r in po[p] if not r['rb']]) / 1e6 for p in PRODAVCY]
    chisla['mediana_rf'] = med
    stroka('медиана выручки РФ, млн', med, '%9.0f')
    sr = [sum(r['score'] for r in po[p]) / max(1, len(po[p])) for p in PRODAVCY]
    chisla['score_sr'] = sr
    stroka('средний балл очереди', sr, '%9.1f')
    srv = [sum(r['ball'] for r in po[p]) / max(1, len(po[p])) for p in PRODAVCY]
    stroka('средняя важность', srv, '%9.1f')
    for reg in DOM:
        v = [sum(1 for i in vybor if raspr[i] == p and region[i] == reg) for p in PRODAVCY]
        chisla['dom_' + reg] = v
        stroka('регион: ' + reg, v)
    return '\n'.join(st), chisla


t_po, ch_po = tablica(prodavec)
print('вариант: ступени ±%d, прочие ±%d, балл ±%d' % VAR)
print(t_po)
for reg, kto in DOM.items():
    chuzh = [i for i in vybor if region[i] == reg and prodavec[i] not in kto]
    assert not chuzh, (reg, chuzh)
for u, e in edinicy.items():
    assert len({prodavec[i] for i in e['novye']}) == 1
    if e['panel']:
        p0 = sorted({vlad[j] for j in e['panel']})[0]
        if prodavec[e['novye'][0]] != p0:
            print('   группа с панелью не у её продавца (правило городов): %s -> %s, панель у %s' % (
                e['novye'], FIO[prodavec[e['novye'][0]]], FIO[p0]))

# ====================================================================== 6. ХОЛДИНГИ В КАТАЛОГ (holding_chlen)
holding_chlen = []
for u, e in edinicy.items():
    vse = e['novye'] + e['panel']
    if len(vse) < 2:
        continue
    gr_panel = None
    for j in e['panel']:
        g_ = panel[j].get('holding_gruppa')
        if g_ and not g_.startswith('snyato'):
            gr_panel = g_
            break
    gid = gr_panel or ('gK-' + min(e['novye']))
    nazv_g = None
    if gr_panel:
        nazv_g = next((panel[j].get('holding') for j in e['panel'] if panel[j].get('holding_gruppa') == gr_panel and panel[j].get('holding')), None)
    if not nazv_g:
        hs = [norm_h(sb.komp[i]['Холдинг (агент)']) for i in e['novye'] if norm_h(sb.komp[i]['Холдинг (агент)'])]
        sayty = [g['sayt'] for g in sb.gruppy if len(set(g['inns']) & set(vse)) > 1]
        nazv_g = (M.s(sb.komp[e['novye'][0]]['Холдинг (агент)']) + ' (по данным составителя файла)') if hs else (
            'общий сайт %s' % sayty[0] if sayty else 'общие номера: %s' % ' / '.join(
                (kompanii.get(x) or panel.get(x) or {}).get('predpriyatie', x)[:30] for x in vse[:3]))
    for i in e['novye']:
        kompanii[i]['holding_gruppa'] = gid
        if not kompanii[i]['holding']:
            kompanii[i]['holding'] = nazv_g
        holding_chlen.append({'gruppa': gid, 'inn': i, 'nazvanie': kompanii[i]['predpriyatie'], 'region': region[i],
                              'segment': kompanii[i]['segment'] or kompanii[i]['segment_meyer7'],
                              'vyruchka_rub': kompanii[i].get('vyruchka_rub'), 'v_vybore': 1,
                              'svyaz': '; '.join(sorted(svyazi[i]))[:500]})
    if not gr_panel:
        for j in e['panel']:            # компания панели в новой группе – строкой группы (её саму не меняем)
            holding_chlen.append({'gruppa': gid, 'inn': j, 'nazvanie': panel[j]['predpriyatie'], 'region': panel[j]['region'],
                                  'segment': panel[j].get('segment'), 'vyruchka_rub': panel[j].get('vyruchka_rub'), 'v_vybore': 1,
                                  'svyaz': '; '.join(sorted(svyazi[j]))[:500]})
print('холдингов (групп 2+ компаний) с новыми: %d, строк holding_chlen %d' % (
    len({h['gruppa'] for h in holding_chlen}), len(holding_chlen)))

# ====================================================================== 7. ПЛАН
for x in kontakty:
    for kk in [kk for kk in x if kk.startswith('_')]:
        del x[kk]
otkaz_vse = dict(OTB['otkaz'])
otkaz_vse.update(otkaz)
plan = {'vremya': time.strftime('%Y%m%d-%H%M%S'), 'nuzhno': NUZHNO, 'prodavcy': prodavec, 'dom': DOM, 'fio': FIO,
        'kompanii': list(kompanii.values()), 'kontakty': kontakty, 'lyudi': lyudi, 'istochniki': istochniki,
        'holding_chlen': holding_chlen, 'novye_kolonki': NOVYE_KOLONKI_COMPANY,
        'stupeni': {i: {'tier': dannye[i]['tier'], 'score': dannye[i]['score'], 'ball': dannye[i]['ball']} for i in vybor},
        'edinicy': {u: e for u, e in edinicy.items() if len(e['novye']) + len(e['panel']) > 1}, 'konflikty': konflikty,
        'otkaz_otbora': otkaz, 'aktivnye_meyer_inn': sorted(AKT_MEYER | {i for i, (pl, _) in IMENA.items() if pl}),
        'tablica': t_po, 'chisla': ch_po, 'milp': VAR, 'imena_vruchnuyu': IMENA,
        'svod': {'vzyato': len(vybor), 'po_gruppam_poryadka': dict(collections.Counter(
            ('пищевка с ЛПР', 'прочие с ЛПР', 'пищевка без ЛПР', 'прочие без ЛПР')[poryadok(K[i])[0]] for i in vybor)),
            'stupen': dict(collections.Counter(dannye[i]['tier'] for i in vybor)), 'rb': sum(dannye[i]['rb'] for i in vybor),
            'vozvrat': sum(dannye[i]['vozvrat'] for i in vybor), 'vor16': sorted(VOR16 & set(vybor)),
            'kontakty': dict(stat_k), 'bez_telefona_v_pule': bez_tel,
            'otkaz_po_prichine': dict(collections.Counter(v[0].split(':')[0] for v in otkaz.values()))}}
io.open(OUT, 'w', encoding='utf-8').write(json.dumps(plan, ensure_ascii=False, indent=0, default=str))
print('ступени: %s; по группам порядка: %s; Беларусь %d; возвращённых из «Не вошли» %d; воронежские из архива: %s' % (
    plan['svod']['stupen'], plan['svod']['po_gruppam_poryadka'], plan['svod']['rb'], plan['svod']['vozvrat'], plan['svod']['vor16']))
print('план: %s (%.0f с)' % (OUT, time.time() - T0))
