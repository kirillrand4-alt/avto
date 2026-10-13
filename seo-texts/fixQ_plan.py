# -*- coding: utf-8 -*-
"""fixQ (локально, только чтение данных): замена 330 «не покупателей Meyer» – план (владелец 13.10: «не покупателей
убрать и добрать», сохранить 270 у meyer1–4 и 120 у meyer5–9, равное качество, домашние регионы, холдинги).

    python3 -E -P fixQ_plan.py <папка fix/Q> <папка fixK> <выход plan.json>

В папке Q: osn/db0 (копии баз СЕЙЧАС, fixQ_vzyat.py), osn/kodroot/app (код панели СЕЙЧАС – с fixR и fixS),
sverka.json (свежая сверка Битрикса fixH_bitrix_sverka по 559 покупателям), dadata_q.json (fixQ_dadata.py),
checko_razbor.json (panel_checko_razbor.py по fixQ-checko-html.zip, если есть), bitrix/ (fixS-bitrix-0910.zip).
В папке fixK: otbor.json (проверенный пул, данные кандидатов), dadata*.json, by*.json, checko/razbor.json,
fixD-holdingi.json. Вердикты: fix/P/svodka.json (1 680 панели), fix/P2/svodka_kand.json (кандидаты), убрать –
fix/P/fixP-ubrat.json.

КАНДИДАТЫ – только «покупатель» по 12 оценщикам (P2). Проверки (как fixK_plan): не в панели и не в архиве (кроме 16
воронежских fixG2), действующая (РФ – DaData + checko, РБ – МНС), выручка от 30 млн если известна (checko, иначе
сборка), нет активной сделки Meyer у самой компании (свежая сверка: ИНН сделки, ИНН в тексте, точное название, УНП),
нет «изделий из первичной гранулы», есть хоть один телефон или ЛПР. Список соседней сессии «Meyer – не покупатель» –
только пометкой (вердикт оценщиков новее и по фактам).
СТУПЕНЬ – формула панели СЕЙЧАС (fixS_ball.razbor_kompanii: ЛПР + метка Битрикса -> не ниже 600) на копии каталога,
куда вставлены кандидаты и прогнан fixS_metki.py (метки КЦ/СЦ/Meyer провалено). Порядок отбора: уверенность
высокая/средняя -> низкая; ступень 800 -> 600 (ЛПР или Битрикс наравне) -> 400 -> 200; пищевка раньше; выручка.
РАЗДАЧА – MILP (scipy/HiGHS): каждому ровно столько новых, сколько у него убрано; единица – группа холдинга/общего
сайта/общих номеров целиком (с группой панели – к её менеджеру), домашние регионы – жёстко; коридоры – по ИТОГОВЫМ
составам (оставшиеся + новые) попарно внутри группы meyer1–4 и группы meyer5–9: ступени 800/600/400/200, «ЛПР с
мобильным или Битрикс», пищевка, Беларусь, «неясно» по вердикту, пороги выручки (-> медиана), средний балл,
домашний регион поровну; сначала не хуже текущего перекоса.
"""
import collections
import csv
import glob
import io
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import time

Q, WK, OUT = sys.argv[1:4]
OSN = os.path.join(Q, 'osn')
ZDES = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ZDES)
import fixK_m7 as M  # noqa: E402

SIM0 = os.path.join(Q, 'sim0')          # копия СЕЙЧАС минус 330 (для «до» – db0 как есть)
SIMA = os.path.join(Q, 'sim_vse')       # + все годные кандидаты (предварительная ступень)
SIMB = os.path.join(Q, 'sim_itog')      # + только отобранные (итог)
for d in (SIM0, SIMA, SIMB):
    os.makedirs(d, exist_ok=True)
for f in ('meyer_baza1.db', 'centro_sales_meyer1.db'):
    shutil.copy(os.path.join(OSN, 'db0', f), os.path.join(SIM0, f))
os.environ['CENTRIFUGAL_DB'] = os.environ['CENTRO_DB'] = os.path.join(OSN, 'db0', 'meyer_baza1.db')
os.environ['CENTRO_SALES_DB'] = os.path.join(OSN, 'db0', 'centro_sales_meyer1.db')
sys.path.insert(0, os.path.join(OSN, 'kodroot'))
from app.services import centro_catalog as cat  # noqa: E402
from app.services import centro_sales as sales  # noqa: E402
import fixE1_regiony_segmenty as E1  # noqa: E402
import fixS_ball as E2  # noqa: E402

T0 = time.time()
DATA = '13.10.2026'
BAZA = 'База 7 (замена 13.10)'
BAZA_OPIS = ('MEYER-7: замена 13.10 вместо компаний, признанных не покупателями Meyer; '
             'каждая проверена оценщиками: покупатель (сортировка / рентген)')
PRODAVCY = ['meyer1', 'meyer2', 'meyer3', 'meyer4', 'meyer5', 'meyer6', 'meyer7', 'meyer8', 'meyer9']
GRUPPY = [['meyer1', 'meyer2', 'meyer3', 'meyer4'], ['meyer5', 'meyer6', 'meyer7', 'meyer8', 'meyer9']]
RAZMER = {p: (270 if p in GRUPPY[0] else 120) for p in PRODAVCY}
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
NE_EDA = ('вторсыр', 'пластм', 'песок', 'гравий', 'камень', 'известняк', 'стекл', 'уголь', 'полимер', 'металл', 'руд',
          'минерал', 'хими', 'лесо', 'дерев', 'торф', 'кирпич', 'цемент', 'бумаг', 'картон', 'текстил', 'резин', 'шин')
IMENA = M.IMENA
NE_TROGAT = {'0306229126', '1829013726', '7224031400', '4238013194', '2354009935', '3915013956', '6605002100', '5406996896',
             '1655471556'}
NE_BRAT = {'5040005678': 'АО «ВБД Напитки»: холдинг в активной сделке Meyer (координатор 13.10) – не беру'}


def eda_po_otrasli(otr):
    o = (otr or '').lower()
    return int(bool(o) and not any(x in o for x in NE_EDA))


def zagr_json(put, umolch=None):
    if not os.path.exists(put):
        if umolch is not None:
            return umolch
        raise SystemExit('нет файла %s' % put)
    return json.load(open(put, encoding='utf-8'))


OTB = zagr_json(os.path.join(WK, 'otbor.json'))
SV = zagr_json(os.path.join(Q, 'sverka.json'))
DD = {}
for f in sorted(glob.glob(os.path.join(WK, 'dadata*.json'))) + [os.path.join(Q, 'dadata_q.json')]:
    for i, z in zagr_json(f, {}).items():
        if not z.get('oshibka') or i not in DD:
            DD[i] = z
BY = {}
for f in sorted(glob.glob(os.path.join(WK, 'by*.json'))):
    o = zagr_json(f, {})
    if isinstance(o, dict):
        BY.update(o)
CH = dict(zagr_json(os.path.join(WK, 'checko', 'razbor.json'), {}))
CHQ = zagr_json(os.path.join(Q, 'checko_razbor.json'), {})
for i, z in CHQ.items():
    if not z.get('oshibka') or i not in CH:
        CH[i] = z
HOLD = zagr_json(os.path.join(WK, 'fixD-holdingi.json'))
SVP = {x['inn']: x for x in zagr_json(os.path.join(M.SCR, 'fix', 'P', 'svodka.json'))}
SK = zagr_json(os.path.join(M.SCR, 'fix', 'P2', 'svodka_kand.json'))
UBR = zagr_json(os.path.join(M.SCR, 'fix', 'P', 'fixP-ubrat.json'))
print('данные: кандидатов-покупателей %d, dadata %d, РБ %d, checko %d (новых %d), вердиктов панели %d' % (
    sum(1 for v in SK.values() if v['verdikt_norm'] == 'покупатель'), len(DD), len(BY), len(CH), len(CHQ), len(SVP)))
pul, m, k3, dop = M.zagruzit()
sb = M.Sborka(pul, m, k3, dop)
print('сборка прочитана (%.0f с)' % (time.time() - T0))

# ---------------------------------------------------------------- активные сделки Meyer (для меток и итоговой проверки)
AKT_MEYER = set()
AKT_UNP = collections.defaultdict(list)
MEYER_CSV = os.path.join(Q, 'bitrix', 'meyer_all.csv')
for r in csv.DictReader(io.open(MEYER_CSV, encoding='utf-8-sig', newline=''), delimiter=';'):
    d9 = re.sub(r'\D', '', r.get('INN') or '')
    d_ = ('0' + d9) if len(d9) in (9, 11) else d9
    if (r.get('АКТИВНА') or '').strip() != 'да':
        continue
    if d_:
        M.KLIENTY.setdefault(d_, (r.get('КОМПАНИЯ') or r.get('НАЗВАНИЕ_В_РЕКВИЗИТАХ') or '')[:80])
        AKT_MEYER.add(d_)
    if len(d9) == 9:
        AKT_MEYER.add(d9)
        AKT_UNP[d9].append('сделка %s %s «%s»: УНП в поле ИНН' % (r['DEAL_ID'], r['ВОРОНКА'], (r['TITLE'] or '')[:60]))
    for t_ in (r.get('TITLE') or '', r.get('КОМПАНИЯ') or '', r.get('НАЗВАНИЕ_В_РЕКВИЗИТАХ') or ''):
        AKT_MEYER.update(re.findall(r'(?<!\d)(\d{12}|\d{10})(?!\d)', t_))
        for x in re.findall(r'(?<!\d)(\d{9})(?!\d)', t_):
            AKT_UNP[x].append('сделка %s %s «%s»: УНП в тексте' % (r['DEAL_ID'], r['ВОРОНКА'], (r['TITLE'] or '')[:60]))
# список соседней сессии «Meyer – не покупатель» – только пометка
NEPOK_INN, NEPOK_DOM = {}, {}
for r in csv.reader(io.open(os.path.join(M.SCR, 'vhod-nepok', 'meyer-ne-pokupateli-1013-1323.csv'), encoding='utf-8-sig'), delimiter=';'):
    if r[0].startswith('ИНН или'):
        continue
    prich = ('список «Meyer – не покупатель» 13.10 (%s): %s' % (r[6], r[7]))[:250]
    if r[1] in ('ИНН', 'УНП'):
        NEPOK_INN[re.sub(r'\D', '', r[0])] = prich
    elif r[1] == 'ключ' and M.domen(r[3]):
        NEPOK_DOM[M.domen(r[3])] = prich


def nepok_pometka(inn):
    prich = NEPOK_INN.get(inn, '')
    if not prich:
        d = M.domen(sb.komp[inn]['Сайт'])
        while d and '.' in d:
            if d in NEPOK_DOM:
                prich = NEPOK_DOM[d] + ' (по домену сайта %s)' % d
                break
            d = d.split('.', 1)[1]
    return (prich + '; оценщики 13.10 (по фактам): покупатель') if prich else ''


# ---------------------------------------------------------------- панель сейчас, убираемые
k0 = sqlite3.connect(os.path.join(OSN, 'db0', 'meyer_baza1.db'))
k0.row_factory = sqlite3.Row
s0 = sqlite3.connect(os.path.join(OSN, 'db0', 'centro_sales_meyer1.db'))
panel_vse = {r['inn']: dict(r) for r in k0.execute('SELECT * FROM company')}
vlad_vse = dict(s0.execute('SELECT inn, username FROM company_assignment').fetchall())
assert set(vlad_vse) == set(panel_vse) and len(panel_vse) == 1680, (len(vlad_vse), len(panel_vse))
arhiv = {r[0] for r in k0.execute('SELECT inn FROM arhiv_company')}
VOR16 = set(OTB['vor16'])
UBRAT = {}
for x in UBR:
    assert vlad_vse[x['inn']] == x['menedzher'], x
    UBRAT[x['inn']] = {'nazvanie': panel_vse[x['inn']]['predpriyatie'], 'prodavec': x['menedzher'], 'prichina': x['prichina']}
CEL = {p: sum(1 for u in UBRAT.values() if u['prodavec'] == p) for p in PRODAVCY}
print('убрать %d: %s' % (len(UBRAT), CEL))
panel = {i: c for i, c in panel_vse.items() if i not in UBRAT}
vlad = {i: p for i, p in vlad_vse.items() if i not in UBRAT}
k = sqlite3.connect(os.path.join(SIM0, 'meyer_baza1.db'))
k.row_factory = sqlite3.Row
for t_ in ('contact', 'person', 'company_source', 'holding_chlen', 'company'):
    k.execute('DELETE FROM %s WHERE inn IN (%s)' % (t_, ','.join('?' * len(UBRAT))), list(UBRAT))
k.commit()
s_ = sqlite3.connect(os.path.join(SIM0, 'centro_sales_meyer1.db'))
s_.execute('DELETE FROM company_assignment WHERE inn IN (%s)' % ','.join('?' * len(UBRAT)), list(UBRAT))
s_.commit()
s_.close()


def region_oficialnyy(inn, c):
    """-> (регион, откуда)."""
    if len(inn) == 9:
        a = (BY.get(inn) or {}).get('vpadres') or ''
        m_ = re.search(r'(Брестская|Витебская|Гомельская|Гродненская|Минская|Могил[её]вская) обл', a)
        if m_:
            return 'Беларусь, %s область' % m_.group(1).replace('Могилевская', 'Могилёвская'), 'адрес в реестре МНС РБ'
        if re.search(r'г\. ?Минск', a):
            return 'Беларусь, Минск', 'адрес в реестре МНС РБ'
        for gor, obl in (('Брест', 'Брестская'), ('Витебск', 'Витебская'), ('Гомел', 'Гомельская'), ('Гродн', 'Гродненская'),
                         ('Могил', 'Могилёвская'), ('Новополоцк', 'Витебская'), ('Полоцк', 'Витебская'), ('Барановичи', 'Брестская'),
                         ('Пинск', 'Брестская'), ('Бобруйск', 'Могилёвская'), ('Борисов', 'Минская'), ('Жодино', 'Минская'),
                         ('Солигорск', 'Минская'), ('Молодечно', 'Минская'), ('Мозыр', 'Гомельская'), ('Лид', 'Гродненская'),
                         ('Орш', 'Витебская'), ('Жлобин', 'Гомельская'), ('Светлогорск', 'Гомельская')):
            if re.search(r'г\. ?' + gor, a):
                return 'Беларусь, %s область' % obl, 'адрес в реестре МНС РБ'
        return 'Беларусь', 'сборка MEYER-7' + (' (адрес МНС РБ: %s)' % a[:60] if a else '')
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
        return False, '', ('статус не проверен: DaData не запрашивалась' if inn not in DD else 'нет в ЕГРЮЛ по DaData')
    if st not in ('ACTIVE', 'REORGANIZING'):
        return False, '', 'ЕГРЮЛ (DaData): %s' % st
    z = CH.get(inn) or {}
    if z and not z.get('oshibka') and z.get('status'):
        n = E1.nedeystvuyushchaya(z['status'])
        if n:
            return False, '', 'checko: ' + n
        return True, z['status'] + (('; правопреемник %s' % z['pravopreemnik']) if z.get('pravopreemnik') else ''), ''
    return True, {'ACTIVE': 'Действующая компания', 'REORGANIZING': 'Действующая, в процессе реорганизации'}[st] + ' (ЕГРЮЛ по DaData)', ''


K = {i: z for i, z in OTB['kandidaty'].items() if (SK.get(i) or {}).get('verdikt_norm') == 'покупатель'}
print('покупателей в проверенном пуле fixK: %d' % len(K))


def vyr_dlya(inn):
    z = CH.get(inn) or {}
    if z.get('vyruchka') is not None and not z.get('oshibka'):
        return float(z['vyruchka'])
    return K[inn]['vyr']


# ====================================================================== 1. ПРОВЕРКИ (без учёта групп)
pomet, otkaz = {}, collections.OrderedDict()
for inn in sorted(K):
    c = sb.komp[inn]
    pr = []
    if inn in panel_vse:
        pr.append('уже в панели')
    if inn in arhiv and inn not in VOR16:
        pr.append('в архиве панели')
    if inn in IMENA and IMENA[inn][0]:
        pr.append('активная сделка Meyer по точному названию (проверено вручную): ' + IMENA[inn][1])
    if inn in NE_BRAT:
        pr.append(NE_BRAT[inn])
    sv = SV['kandidaty'].get(inn) or {}
    if sv.get('aktivnye_meyer'):
        a = sv['aktivnye_meyer'][0]
        pr.append('активная сделка Meyer (%s): %s %s «%s»' % (a['kak'], a['id'], a['voronka'], a['title'][:60]))
    elif sv.get('po_imeni_proverit') and not (inn in IMENA and not IMENA[inn][0]):
        a = sv['po_imeni_proverit'][0]
        pr.append('возможна активная сделка Meyer по точному названию: %s «%s» – не беру без проверки' % (a['id'], a['title'][:60]))
    if len(inn) == 9 and AKT_UNP.get(inn):
        pr.append('активная сделка Meyer (Беларусь, по УНП): ' + AKT_UNP[inn][0])
    if inn in AKT_MEYER:
        pr.append('активная сделка Meyer (ИНН в сделке)')
    pl_ = M.izdeliya_iz_pervichnoy(c)
    if pl_:
        pr.append(pl_)
    v_ = vyr_dlya(inn)
    if v_ is not None and v_ < 3e7:
        pr.append('выручка %.1f млн по checko – меньше 30 млн (владелец 13.10)' % (v_ / 1e6))
    ok, st_tekst, prich = status_proverka(inn)
    if not ok:
        pr.append(prich if prich.startswith('статус не проверен') else 'недействующая: ' + prich)
    if K[inn]['tier'] < 2 and not K[inn]['n_tel'] and not int((SV['kandidaty'].get(inn) or {}).get('bitrix_kc') or 0):
        pr.append('нет ни одного телефона и ЛПР')
    if pr:
        otkaz[inn] = pr
        continue
    reg, reg_ist = region_oficialnyy(inn, c)
    pomet[inn] = {'status': st_tekst, 'region': reg, 'region_istochnik': reg_ist, 'nepokupatel': nepok_pometka(inn)}
godnye = sorted(pomet)
print('проверки: годных %d, отказ %d: %s' % (len(godnye), len(otkaz), dict(collections.Counter(
    v[0].split(':')[0].split(' (')[0][:50] for v in otkaz.values()))))


# ====================================================================== 2. СТРОКИ КАТАЛОГА (как fixK_plan)
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
VERDIKT_KOLONKI = [('meyer_verdikt', 'TEXT'), ('meyer_verdikt_napravlenie', 'TEXT'), ('meyer_verdikt_uverennost', 'TEXT'),
                   ('meyer_verdikt_pochemu', 'TEXT'), ('meyer_verdikt_dokaz', 'TEXT'), ('meyer_verdikt_data', 'TEXT')]
NOVYE_KOLONKI_COMPANY = VERDIKT_KOLONKI


def verdikt_polya(v):
    napr = (v.get('napravlenie') or '').strip()
    return {'meyer_verdikt': (v.get('verdikt_norm') or v.get('verdikt') or '').strip(),
            'meyer_verdikt_napravlenie': '' if napr in ('-', '—') else napr,
            'meyer_verdikt_uverennost': (v.get('uverennost') or '').strip(),
            'meyer_verdikt_pochemu': (v.get('pochemu') or '').strip()[:1500],
            'meyer_verdikt_dokaz': (v.get('dokazatelstvo') or '').strip()[:1500], 'meyer_verdikt_data': DATA}


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
           'bazy': BAZA, 'bazy_opisanie': BAZA_OPIS, 'v_baze_obzvona': None, 'has_signal': 0, 'n_signals': 0, 'n_facts': 0}
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
    osn = row['okved']
    dopk = [x.strip() for x in M.s(c['Доп. ОКВЭД']).split(',') if x.strip()]
    row['okvedy_vse'] = ' | '.join([osn] + [x for x in dopk if x != osn]) if osn else ' | '.join(dopk)
    seg = E1.segs(E1.segment_tz(osn))
    row['segment'] = row['segment_osn'] = ' | '.join(seg)
    iz_dop = E1.poryadok([s2 for k_ in dopk for s2 in E1.segs(E1.segment_tz(k_)) if s2 not in seg])
    row['segment_dop'] = ' | '.join(iz_dop)
    row['segment_meyer7'] = M.s(c['Сегмент'])
    row['segment_kak'] = M.s(c['Как определён сегмент'])
    row['popadanie'] = ('основной ОКВЭД' if (seg or 'основн' in row['segment_kak']) else
                        'по сайту (Беларусь, ОКЭД не загружен)' if rb else 'только доп. ОКВЭД')
    row['otrasl'] = otrasl(osn, row['segment_meyer7'])
    row['pometka_ocheredi'] = ''
    poy = sb.poyasneniya.get(inn) or {}
    row['opisanie'] = M.s(c['Описание (по сайту)']) or M.s(poy.get('Пояснение агента'))[:1500]
    row['produkciya'] = M.s(c['Продукция'])
    for kol, nazv in PASPORT:
        row[kol] = M.s(c[nazv])
    row['poyasnenie_agenta'] = ' · '.join(x for x in (M.s(poy.get('Пояснение агента')), ('доказательство: ' + M.s(poy.get('Доказательство')))
                                                    if M.s(poy.get('Доказательство')) else '') if x)[:3000] or None
    sp = sb.spornye.get(inn) or {}
    row['spornyy_sayt'] = ('%s: %s' % (M.s(sp.get('Кто сомневается')), M.s(sp.get('Почему'))))[:1500] if sp else None
    vid_s, sila = M.sayt_prinyat(c['Сайт: чей'])
    row['proverka_sayta'] = vid_s
    row['sayt_chey'] = ('Проверка сборки MEYER-7 %s: %s' % (DATA, M.s(c['Сайт: чей'])))[:1500]
    row['inn_nayden_po_saytu'] = M.s(c['ИНН найден по сайту: юрлицо']) or None
    row['reviziya_profil'] = ' | '.join(x for x in (M.s(c['Ревизия: профиль']), pm.get('nepokupatel') or '') if x) or None
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
    row.update(verdikt_polya(SK[inn]))
    return row, pochty_checko


KESH = {}
stat_k = collections.Counter()


def stroki(inn):
    if inn in KESH:
        return KESH[inn]
    row, pch = stroka_kompanii(inn)
    kont, lyud, pochty, zh = M.kontakty_kompanii(sb, inn, cat)
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
    v = SK[inn]
    ist_.append({'inn': inn, 'field_name': 'Покупатель Meyer: %s (%s)' % (v.get('verdikt_norm'), v.get('napravlenie') or '—'),
                 'source': ('оценщики 13.10, кусок %s: %s' % (v.get('kusok'), v.get('dokazatelstvo') or ''))[:500], 'source_url': ''})
    for x in kont:
        if x.get('_lpr') and x.get('source_url'):
            ist_.append({'inn': inn, 'field_name': 'ЛПР: %s' % (x.get('position') or x['_rol']),
                         'source': 'сайт компании (MEYER-7 13.10)', 'source_url': x['source_url'].split(' ; ')[0]})
    ist = ['сборка MEYER-7 13.10', 'оценщики «покупатель Meyer» 13.10']
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


for inn in godnye:
    stroki(inn)
print('строки кандидатов собраны (%.0f с)' % (time.time() - T0))


# ====================================================================== 3. КОПИЯ КАТАЛОГА: ВСТАВКА, МЕТКИ fixS, СТУПЕНЬ
def vstavit(papka, inny):
    """Копия sim0 -> papka, вставка строк кандидатов inny, fixS_metki --primenit на копии."""
    for f in ('meyer_baza1.db', 'centro_sales_meyer1.db'):
        shutil.copy(os.path.join(SIM0, f), os.path.join(papka, f))
    kk = sqlite3.connect(os.path.join(papka, 'meyer_baza1.db'))
    kc = {r[1] for r in kk.execute('PRAGMA table_info(company)')}
    for kol, tip in NOVYE_KOLONKI_COMPANY:
        if kol not in kc:
            kk.execute('ALTER TABLE company ADD COLUMN %s %s' % (kol, tip))
    kc = {r[1] for r in kk.execute('PRAGMA table_info(company)')}
    kol_k = {r[1] for r in kk.execute('PRAGMA table_info(contact)')}
    kol_p = {r[1] for r in kk.execute('PRAGMA table_info(person)')}
    lishnie = sorted({x for i in inny for x in KESH[i]['row']} - kc)
    assert not lishnie, 'колонок нет в каталоге: %s' % lishnie
    for i in inny:
        r = KESH[i]['row']
        kk.execute('INSERT INTO company (%s) VALUES (%s)' % (','.join('"%s"' % x for x in r), ','.join('?' * len(r))), list(r.values()))
        for x in KESH[i]['kont']:
            rr = {a: v for a, v in x.items() if a in kol_k and not a.startswith('_')}
            kk.execute('INSERT INTO contact (%s) VALUES (%s)' % (','.join(rr), ','.join('?' * len(rr))), list(rr.values()))
        for x in KESH[i]['lyud']:
            rr = {a: v for a, v in x.items() if a in kol_p}
            kk.execute('INSERT INTO person (%s) VALUES (%s)' % (','.join(rr), ','.join('?' * len(rr))), list(rr.values()))
    kk.commit()
    kk.close()
    env = dict(os.environ, FIXS_KOREN=papka, FIXS_KAT=os.path.join(papka, 'meyer_baza1.db'),
               FIXS_SALES=os.path.join(papka, 'centro_sales_meyer1.db'), FIXS_DROP=papka)
    r = subprocess.run([sys.executable, '-I', os.path.join(ZDES, 'fixS_metki.py'), '--primenit', '--zip',
                        os.path.join(Q, 'dl', 'fixS-bitrix-0910.zip')], capture_output=True, text=True, env=env, timeout=1200)
    if r.returncode:
        raise SystemExit('fixS_metki на копии: %s %s' % (r.stdout[-1500:], r.stderr[-1500:]))
    return r.stdout


def ocenit(papka, inny, novye):
    """fixS_ball.razbor_kompanii по копии papka; у новых – сначала флаги ЛПР (как при заливке). -> {inn: d}, {inn: флаги}."""
    os.environ['CENTRIFUGAL_DB'] = os.environ['CENTRO_DB'] = os.path.join(papka, 'meyer_baza1.db')
    os.environ['CENTRO_SALES_DB'] = os.path.join(papka, 'centro_sales_meyer1.db')
    kesh = {}
    orig = cat._shared_phone_keys

    def _sh(conn):
        if 'k' not in kesh:
            kesh['k'] = orig(conn)
        return kesh['k']
    cat._shared_phone_keys = _sh
    kk = sqlite3.connect(os.path.join(papka, 'meyer_baza1.db'))
    kk.row_factory = sqlite3.Row
    out, fl = {}, {}
    try:
        for inn in inny:
            c = dict(kk.execute('SELECT * FROM company WHERE inn=?', (inn,)).fetchone())
            items = cat.contacts(inn)
            if inn in novye:
                f = M.flagi(cat, items)
                f['search_blob'] = M.search_blob(cat, inn, c, items, f['lpr_kratko'])
                c.update(f)
                fl[inn] = f
            d = E2.razbor_kompanii(c, items, cat, sales)
            d['eda'] = eda_po_otrasli(c.get('otrasl'))
            d['rb'] = int(len(inn) == 9 or (c.get('strana') or '') == 'Беларусь')
            d['n_tel'] = sum(1 for x in items if x['kind'] == 'phone')
            d['neyasno'] = int(((SK.get(inn) or SVP.get(inn) or {}).get('verdikt_norm') or (SVP.get(inn) or {}).get('verdikt') or '') == 'неясно')
            d['bx_kolonki'] = {p: c.get(p) for p in ('bitrix_kc_est', 'bitrix_sc_est', 'bitrix_meyer_provaleno', 'bitrix_meyer_uspeshno',
                                                     'bitrix_metki', 'bitrix_metki_podrobno', 'bitrix_metki_istochnik',
                                                     'bitrix_kc', 'bitrix_kc_info', 'bitrix_sdelok', 'bitrix_klient_sc',
                                                     'bitrix_klient_meyer', 'bitrix_v_rabote', 'bitrix_poslednyaya')}
            out[inn] = d
    finally:
        cat._shared_phone_keys = orig
        kk.close()
    return out, fl


# «до»: панель сейчас (db0, 1 680) – формула fixS
DO, _ = ocenit(os.path.join(OSN, 'db0'), sorted(panel_vse), set())
s_db0 = dict(s0.execute('SELECT inn, assignment_score FROM company_assignment').fetchall())
st_db0 = dict(s0.execute('SELECT inn, stupen_ocheredi FROM company_assignment').fetchall())
rash_do = [i for i in DO if abs(float(s_db0[i]) - DO[i]['score']) > 0.05 or int(st_db0[i] or 0) != DO[i]['tier']]
print('«до»: формула fixS на db0 против базы продаж – расхождений балла/ступени %d %s (%.0f с)' % (
    len(rash_do), [(i, s_db0[i], DO[i]['score'], st_db0[i], DO[i]['tier']) for i in rash_do[:5]], time.time() - T0))
out_a = vstavit(SIMA, godnye)
print('копия «все годные»: fixS_metki: %s' % ' | '.join(x for x in out_a.splitlines() if 'ВСЕГО' in x or 'активных' in x)[:400])
PRED, _ = ocenit(SIMA, sorted(panel) + godnye, set(godnye))
print('предварительная ступень годных (%d): %s; поднято Битриксом %d (%.0f с)' % (
    len(godnye), dict(collections.Counter(E2.STUPEN[PRED[i]['tier']] for i in godnye)), sum(PRED[i]['bx_podnyal'] for i in godnye),
    time.time() - T0))

# ====================================================================== 4. ОТБОР С ГРУППАМИ
UV = {'высокая': 0, 'средняя': 0, 'низкая': 1}


def poryadok(inn):
    d = PRED[inn]
    return (UV.get(SK[inn].get('uverennost'), 1), -d['tier'], 0 if d['eda'] else 1, -(vyr_dlya(inn) or 0), -K[inn]['sila_sayta'], inn)


ochered = sorted((i for i in godnye if PRED[i]['n_tel'] > 0 or PRED[i]['bx_est']), key=poryadok)
for i in godnye:
    if i not in ochered:
        otkaz[i] = ['в карточке нет ни одного телефона (и метки Битрикса нет)']
ochered_mesto = {i: n for n, i in enumerate(ochered)}
VSEGO = sum(CEL.values())


def norm_h(h):
    h = M.s(h).lower()
    h = re.sub(r'\(.*?\)', ' ', h)
    h = re.sub(r'\b(ооо|ао|пао|зао|оао|гк|группа компаний|холдинг|агрохолдинг)\b', ' ', h)
    h = re.sub(r'[«»"\'“”„.,]', ' ', h)
    return ' '.join(h.split())


NOM_PANELI = collections.defaultdict(set)
for r in k.execute("SELECT inn, value FROM contact WHERE kind='phone' AND TRIM(COALESCE(chuzhoy_istochnik,''))=''"):
    kk_ = cat._phone_key(r['value'])
    if kk_:
        NOM_PANELI[kk_].add(r['inn'])
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
    for kk2, inns in NOM_PANELI.items():
        po_nom[kk2] |= inns
    for i in vybor:
        for x in KESH[i]['kont']:
            if not M.s(x.get('chuzhoy_istochnik')):
                kk2 = cat._phone_key(x['value'])
                if kk2:
                    po_nom[kk2].add(i)
    for kk2, inns in po_nom.items():
        if len(inns) > 1 and inns & VYB:
            inns = sorted(inns)
            for i in inns:
                svyazi[i].add('общий номер …%s с %s' % (kk2[-4:], ', '.join(x for x in inns if x != i)[:120]))
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
                isk[i] = 'группа связана с компаниями панели у разных менеджеров (%s) – не беру, чтобы не рвать холдинг' % prod_panel
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
            glav = max(po_reg, key=lambda r_: (len(po_reg[r_]), -min(ochered_mesto[i] for i in po_reg[r_])))
            for reg, chl in po_reg.items():
                if reg != glav:
                    for i in chl:
                        isk[i] = ('в одной группе с компаниями региона %s (только %s), а регион %s – только %s: '
                                  'не беру' % (glav, ', '.join(FIO[p] for p in DOM[glav]), reg, ', '.join(FIO[p] for p in DOM[reg])))
            continue
        dop_[u] = sorted(mozhno)
    return edinicy, svyazi, dop_, isk


isklyuchit = {}
for popytka in range(12):
    kand = [i for i in ochered if i not in isklyuchit]
    edinicy, svyazi, dop_, isk = gruppy(kand)
    print('проход %d: кандидатов %d, единиц %d, конфликтов «холдинг – город»: %d' % (popytka + 1, len(kand), len(edinicy), len(isk)))
    if not isk:
        break
    isklyuchit.update(isk)
else:
    raise SystemExit('конфликты групп не сошлись')
for i, pr in isklyuchit.items():
    otkaz[i] = [pr]
region = {i: pomet[i]['region'] for i in kand}
region.update({i: panel[i]['region'] for i in panel})

# ====================================================================== 5. ОТБОР И РАЗДАЧА ОДНИМ MILP (по итоговым составам)
# Новые почти все на ступени 600 (метка Битрикса), а убранные у менеджеров разные по ступеням – поэтому сначала
# отобрать, потом раздать нельзя (проба: неразрешимо). Здесь отбор и раздача – одна задача: из всех годных выбрать
# ровно квоту каждому, чтобы ИТОГОВЫЕ 270/120 были ровными; при прочих равных – уверенность высокая/средняя, затем
# ступень, пищевка, выручка. Коридоры мягкие: до перекоса «сейчас» – лёгкий штраф, сверх него – тяжёлый.
import numpy as np  # noqa: E402
from scipy.optimize import Bounds, LinearConstraint, milp  # noqa: E402

U = sorted(edinicy)
idx = {}
for u in U:
    for p in dop_[u]:
        idx[(u, p)] = len(idx)
nx = len(idx)
METRIKI = [('t4', 'ступень 800', lambda r: int(r['tier'] == 4)), ('t3', 'ступень 600', lambda r: int(r['tier'] == 3)),
           ('t2', 'ступень 400', lambda r: int(r['tier'] == 2)), ('t1', 'ступень 200', lambda r: int(r['tier'] == 1)),
           ('mob_bx', 'ЛПР с мобильным или Битрикс (600+)', lambda r: int(r['tier'] in (3, 4))),
           ('eda', 'пищевка/агро', lambda r: r['eda']), ('rb', 'Беларусь', lambda r: r['rb'])]
STUPENI = {'t4', 't3', 't2', 't1', 'mob_bx'}
METRIKI.append(('rf_vyr', 'РФ с известной выручкой', lambda r: int(not r['rb'] and bool(r['vyr']))))
# пороги выручки – свои у каждой группы, густо около её медианы (иначе медиана «гуляет» между порогами)
GR_METRIKI = {}
for g, chl in enumerate(GRUPPY):
    rf_vyr = sorted(PRED[i]['vyr'] for i in [j for j in panel if vlad[j] in chl] if not PRED[i]['rb'] and PRED[i]['vyr'])   # по оставшимся
    for q in (0.25, 0.75):
        t = rf_vyr[int(len(rf_vyr) * q)]
        kl = 'vyr%d_%d' % (g + 1, int(q * 100))
        GR_METRIKI[kl] = g
        METRIKI.append((kl, 'гр.%d: выручка РФ ниже %.0f млн' % (g + 1, t / 1e6),
                        (lambda tt: (lambda r: int(not r['rb'] and bool(r['vyr']) and r['vyr'] < tt)))(t)))
TOLKO_TABLICA = [('neyasno', 'вердикт «неясно» (у новых 0)', lambda r: r['neyasno'])]
baza = {p: [i for i in panel if vlad[i] == p] for p in PRODAVCY}


def rasbros(raspr, dannye, f):
    out = {}
    for g, chl in enumerate(GRUPPY):
        v = [sum(f(dannye[i]) for i, p in raspr.items() if p == q and i in dannye) for q in chl]
        out[g] = max(v) - min(v)
    return out


def rasbros_sr(raspr, dannye):
    out = {}
    for g, chl in enumerate(GRUPPY):
        v = []
        for q in chl:
            sp = [dannye[i]['score'] for i, p in raspr.items() if p == q and i in dannye]
            v.append(sum(sp) / max(1, len(sp)))
        out[g] = max(v) - min(v)
    return out


DO_RASBROS = {kl: rasbros(vlad_vse, DO, f) for kl, _, f in METRIKI + TOLKO_TABLICA}
DO_RASBROS['score'] = rasbros_sr(vlad_vse, DO)
DO_RASBROS_MED = {}
for g, chl in enumerate(GRUPPY):
    meds = [E2.mediana([DO[i]['vyr'] for i, p in vlad_vse.items() if p == q and not DO[i]['rb']]) for q in chl]
    DO_RASBROS_MED[g] = max(meds) - min(meds)
DO_REG = {}
for reg, kto in DOM.items():
    for g, chl in enumerate(GRUPPY):
        kk3 = [p for p in kto if p in chl]
        if len(kk3) > 1:
            v = [sum(1 for i, p in vlad_vse.items() if p == q and panel_vse[i]['region'] == reg) for q in kk3]
            DO_REG[(reg, g)] = (kk3, max(v) - min(v))
print('перекос СЕЙЧАС (max-min внутри группы meyer1–4 / meyer5–9): %s; средний балл %s; домашние регионы %s' % (
    {kl: (v[0], v[1]) for kl, v in DO_RASBROS.items() if kl != 'score'},
    tuple(round(x, 1) for x in DO_RASBROS['score'].values()), {'%s/%d' % (r, g): v[1] for (r, g), v in DO_REG.items()}))


def kachestvo(i):
    d = PRED[i]
    uv = 60 if SK[i].get('uverennost') in ('высокая', 'средняя') else 0
    v = vyr_dlya(i) or 0
    return uv + {4: 40, 3: 30, 2: 15, 1: 0, 0: -50}[d['tier']] + 3 * d['eda'] + (min(4.0, max(0.0, 2 * np.log10(v / 3e7))) if v > 0 else 0)


L_LEGKO, L_TYAZH = {'st': 8.0, 'pr': 4.0, 'ball': 6.0, 'reg': 8.0}, 2000.0


def med_chisla(f_le):
    """по единицам и базе: (число РФ с известной выручкой, число с выручкой ниже/не выше порога)."""
    nn = {u: sum(1 for i in edinicy[u]['novye'] if not PRED[i]['rb'] and PRED[i]['vyr'] is not None) for u in U}
    bl = {u: sum(1 for i in edinicy[u]['novye'] if not PRED[i]['rb'] and PRED[i]['vyr'] is not None and f_le(PRED[i]['vyr'])) for u in U}
    bn = {p: sum(1 for i in baza[p] if not PRED[i]['rb'] and PRED[i]['vyr'] is not None) for p in PRODAVCY}
    bb = {p: sum(1 for i in baza[p] if not PRED[i]['rb'] and PRED[i]['vyr'] is not None and f_le(PRED[i]['vyr'])) for p in PRODAVCY}
    return nn, bl, bn, bb


def reshit(vremya=600, mediana=None):
    # переменные: x(u,p) – двоичные; затем по каждому коридору (метрика, группа) два «излишка»: e1 – до перекоса сейчас
    # (лёгкий штраф), e2 – сверх него (тяжёлый)
    koridory = []
    for kl, _, f in METRIKI:
        for g, chl in enumerate(GRUPPY):
            if GR_METRIKI.get(kl, g) != g:
                continue
            koridory.append((kl, g, chl, {u: sum(f(PRED[i]) for i in edinicy[u]['novye']) for u in U},
                             {p: sum(f(PRED[i]) for i in baza[p]) for p in PRODAVCY}, 1.0, max(0, DO_RASBROS[kl][g] - 1),
                             L_LEGKO['st' if kl in STUPENI else 'pr']))
    for g, chl in enumerate(GRUPPY):
        koridory.append(('score', g, chl, {u: sum(PRED[i]['score'] for i in edinicy[u]['novye']) for u in U},
                         {p: sum(PRED[i]['score'] for i in baza[p]) for p in PRODAVCY}, 2.0 * RAZMER[chl[0]],
                         max(0.0, DO_RASBROS['score'][g] - 2.0) * RAZMER[chl[0]], L_LEGKO['ball'] / RAZMER[chl[0]]))
    for (reg, g), (kk3, w0) in DO_REG.items():
        koridory.append(('reg:' + reg, g, kk3, {u: sum(1 for i in edinicy[u]['novye'] if region[i] == reg) for u in U},
                         {p: sum(1 for i in baza[p] if region[i] == reg) for p in PRODAVCY}, 1.0, max(0, w0 - 1), L_LEGKO['reg']))
    ne = 2 * len(koridory) + (4 if mediana else 0)
    n = nx + ne
    c = np.zeros(n)
    for (u, p), j in idx.items():
        c[j] = -sum(kachestvo(i) for i in edinicy[u]['novye'])
    ub = np.ones(n)
    for kn, kr in enumerate(koridory):
        c[nx + 2 * kn] = kr[7]
        c[nx + 2 * kn + 1] = L_TYAZH / (RAZMER[kr[2][0]] if kr[0] == 'score' else 1.0)
        ub[nx + 2 * kn] = kr[6]
        ub[nx + 2 * kn + 1] = np.inf
    A, lo, hi = [], [], []
    for u in U:
        row = np.zeros(n)
        for p in dop_[u]:
            row[idx[(u, p)]] = 1
        A.append(row); lo.append(0 if not edinicy[u]['panel'] else 0); hi.append(1)
    for p in PRODAVCY:
        row = np.zeros(n)
        for u in U:
            if (u, p) in idx:
                row[idx[(u, p)]] = len(edinicy[u]['novye'])
        A.append(row); lo.append(CEL[p]); hi.append(CEL[p])
    for kn, (kl, g, chl, fu, base, w, _w1, _l) in enumerate(koridory):
        for a_ in range(len(chl)):
            for b_ in range(a_ + 1, len(chl)):
                p, q = chl[a_], chl[b_]
                row = np.zeros(n)
                for u in U:
                    if (u, p) in idx:
                        row[idx[(u, p)]] += fu[u]
                    if (u, q) in idx:
                        row[idx[(u, q)]] -= fu[u]
                d0 = base[p] - base[q]
                r1 = row.copy(); r1[nx + 2 * kn] = -1; r1[nx + 2 * kn + 1] = -1
                A.append(r1); lo.append(-np.inf); hi.append(w - d0)
                r2 = row.copy(); r2[nx + 2 * kn] = 1; r2[nx + 2 * kn + 1] = 1
                A.append(r2); lo.append(-w - d0); hi.append(np.inf)
    if mediana:
        # медиана выручки РФ у каждого менеджера группы g – в полосе [L, H]: ниже L – меньше половины, не выше H – больше
        # половины (2·ниже − n ≤ −1; 2·не_выше − n ≥ 2); недобор – штраф L_MED за компанию
        for g, (L, Hh) in mediana.items():
            jL, jH = nx + 2 * len(koridory) + 2 * g, nx + 2 * len(koridory) + 2 * g + 1
            c[jL] = c[jH] = L_MED
            ub[jL] = ub[jH] = np.inf
            nn, bl, bn, bb = med_chisla(lambda v: v < L)
            _, le, _, bl2 = med_chisla(lambda v: v <= Hh)
            for p in GRUPPY[g]:
                row = np.zeros(n)
                row2 = np.zeros(n)
                for u in U:
                    if (u, p) in idx:
                        row[idx[(u, p)]] = 2 * bl[u] - nn[u]
                        row2[idx[(u, p)]] = 2 * le[u] - nn[u]
                row[jL] = -1
                A.append(row); lo.append(-np.inf); hi.append(-1 - (2 * bb[p] - bn[p]))
                row2[jH] = 1
                A.append(row2); lo.append(2 - (2 * bl2[p] - bn[p])); hi.append(np.inf)
    integ = np.concatenate([np.ones(nx), np.zeros(ne)])
    r_ = milp(c, constraints=LinearConstraint(np.array(A), lo, hi), integrality=integ, bounds=Bounds(np.zeros(n), ub),
              options={'time_limit': vremya, 'mip_rel_gap': 1e-4})
    return r_, koridory


L_MED = 1500.0
res1, KORIDORY = reshit(vremya=200)
print('MILP проход 1 (без медианы): %s (%.0f с)' % (res1.message[:80], time.time() - T0))
if res1.x is None:
    raise SystemExit('раскладка не найдена')
MEDIANA = {}
for g, chl in enumerate(GRUPPY):
    meds = []
    for p in chl:
        v = [PRED[i]['vyr'] for i in baza[p] if not PRED[i]['rb'] and PRED[i]['vyr'] is not None]
        v += [PRED[i]['vyr'] for (u, q), j in idx.items() if q == p and res1.x[j] > 0.5 for i in edinicy[u]['novye']
              if not PRED[i]['rb'] and PRED[i]['vyr'] is not None]
        meds.append(E2.mediana(v))
    centr = sorted(meds)[len(meds) // 2]
    shir = max(20e6, 0.95 * DO_RASBROS_MED[g])
    MEDIANA[g] = (centr - shir / 2, centr + shir / 2)
print('медиана: проход 1 по менеджерам -> полоса %s' % {g: '%.0f–%.0f млн' % (a / 1e6, b / 1e6) for g, (a, b) in MEDIANA.items()})
res, luchshiy = None, None
for sdvig in (0, 15e6, -15e6, 30e6, -30e6):
    med_ = {g: (a + sdvig, b + sdvig) for g, (a, b) in MEDIANA.items()}
    r_, KORIDORY = reshit(vremya=300, mediana=med_)
    nedobor = float(sum(r_.x[nx + 2 * len(KORIDORY):])) if r_.x is not None else 1e9
    print('MILP (отбор + раздача, медиана в полосе, сдвиг %+.0f млн): %s; недобор %.1f (%.0f с)' % (
        sdvig / 1e6, r_.message[:60], nedobor, time.time() - T0))
    if r_.x is not None and (luchshiy is None or nedobor < luchshiy - 1e-6):
        res, luchshiy, MEDIANA_ITOG = r_, nedobor, med_
    if luchshiy is not None and luchshiy < 1e-6:
        break
if res is None:
    res, MEDIANA_ITOG = res1, {}
MEDIANA = MEDIANA_ITOG
if res.x is None:
    raise SystemExit('раскладка не найдена')
prodavec = {}
for (u, p), j in idx.items():
    if res.x[j] > 0.5:
        for i in edinicy[u]['novye']:
            prodavec[i] = p
vybor = sorted(prodavec, key=lambda i: ochered_mesto[i])
assert collections.Counter(prodavec.values()) == collections.Counter(CEL), collections.Counter(prodavec.values())
VAR = {'status': res.message[:80], 'mediana_polosa': MEDIANA, 'mediana_nedobor': [round(float(x), 2) for x in res.x[nx + 2 * len(KORIDORY):]],
       'izlishki': {'%s/%d' % (kr[0], kr[1]): [round(float(res.x[nx + 2 * kn]), 2),
                                                                         round(float(res.x[nx + 2 * kn + 1]), 2)]
                                               for kn, kr in enumerate(KORIDORY) if res.x[nx + 2 * kn] > 1e-6 or res.x[nx + 2 * kn + 1] > 1e-6}}
print('излишки коридоров (лёгкий, тяжёлый): %s; недобор медианы: %s' % (VAR['izlishki'], VAR['mediana_nedobor']))
ne_ponadobilis = [i for i in kand if i not in prodavec]
print('отбор: взято %d из %d годных (не понадобились %d); конфликтов %d; по уверенности %s; предв. ступень %s' % (
    len(vybor), len(kand), len(ne_ponadobilis), len(isklyuchit), dict(collections.Counter(SK[i]['uverennost'] for i in vybor)),
    dict(collections.Counter(E2.STUPEN[PRED[i]['tier']] for i in vybor))))
edinicy = {u: e for u, e in edinicy.items() if e['novye'][0] in prodavec}

# ====================================================================== 6. ИТОГОВАЯ КОПИЯ: ступень всех 1 680
out_b = vstavit(SIMB, vybor)
print('итоговая копия: fixS_metki: %s' % ' | '.join(x for x in out_b.splitlines() if 'ВСЕГО' in x or 'активных' in x)[:400])
POSLE, flagi_novyh = ocenit(SIMB, sorted(panel) + vybor, set(vybor))
izm_star = [i for i in panel if (POSLE[i]['tier'], round(POSLE[i]['score'], 1)) != (DO[i]['tier'], round(DO[i]['score'], 1))]
print('у оставшихся после вставки новых изменились ступень/балл: %d %s' % (
    len(izm_star), [(i, DO[i]['tier'], POSLE[i]['tier'], DO[i]['score'], POSLE[i]['score']) for i in izm_star[:6]]))
print('ступень новых в итоговой копии против предварительной: %s' % sorted(collections.Counter(
    (PRED[i]['tier'], POSLE[i]['tier']) for i in vybor).items()))
kompanii = {i: dict(KESH[i]['row']) for i in vybor}
for i in vybor:
    kompanii[i].update(flagi_novyh[i])
    kompanii[i]['moy_prioritet'], kompanii[i]['prioritet_pochemu'] = POSLE[i]['ball'], POSLE[i]['pochemu']
    kompanii[i]['stupen_prichina'] = POSLE[i]['stupen_prichina']
    kompanii[i]['kachestvo_nomera'] = {4: 'ЛПР мобильный', 3: 'ЛПР мобильный', 2: 'ЛПР рабочий / с добавочным',
                                       1: 'ЛПР не найден', 0: 'ЛПР не найден'}[POSLE[i]['tier_lpr']]
    for p, v in POSLE[i]['bx_kolonki'].items():          # метки fixS_metki и поля fixH – как на копии
        kompanii[i][p] = v
POSLE_RASPR = dict(vlad)
POSLE_RASPR.update(prodavec)
# запас на случай, если по убираемой появятся действия менеджера (её тогда не убираем): у этого менеджера не вставлять
# столько же новых – одиночки без групп, с конца по качеству
ZAPAS = {p: [i for i in sorted((i for i in vybor if prodavec[i] == p), key=lambda i: (kachestvo(i), i))
             if not any(i in e['novye'] and (len(e['novye']) > 1 or e['panel']) for e in edinicy.values())] for p in PRODAVCY}


def tablica(raspr, dannye, zagolovok):
    po = {p: [dannye[i] for i, u in raspr.items() if u == p and i in dannye] for p in PRODAVCY}
    st = [zagolovok, '%-34s %s' % ('', ' '.join('%9s' % FIO[p][:9] for p in PRODAVCY)) + '   разброс 1–4 / 5–9']
    chisla = {}

    def stroka(nazv, v, fmt='%9d'):
        r1 = max(v[:4]) - min(v[:4])
        r2 = max(v[4:]) - min(v[4:])
        st.append('%-34s %s   %s / %s' % (nazv[:34], ' '.join(fmt % x for x in v), (fmt % r1).strip(), (fmt % r2).strip()))
    v = [len(po[p]) for p in PRODAVCY]
    chisla['n'] = v
    stroka('компаний', v)
    for kl, nazv, f in METRIKI + TOLKO_TABLICA + [('bx_podnyal', 'из 600 поднято Битриксом', lambda r: r['bx_podnyal']),
                                  ('lpr_mob', 'ЛПР с мобильным (по ЛПР)', lambda r: int(r['tier_lpr'] in (3, 4))),
                                  ('t0', 'пометка очереди (0)', lambda r: r['pometka'])]:
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
    chisla['ball_sr'] = srv
    stroka('средняя важность', srv, '%9.1f')
    for reg in DOM:
        v = [sum(1 for i, u in raspr.items() if u == p and i in dannye and region.get(i, (panel_vse.get(i) or {}).get('region')) == reg)
             for p in PRODAVCY]
        chisla['dom_' + reg] = v
        stroka('регион: ' + reg, v)
    return '\n'.join(st), chisla


t_do, ch_do = tablica(vlad_vse, DO, 'ДО (панель сейчас, 1 680; формула fixS)')
t_po, ch_po = tablica(POSLE_RASPR, POSLE, 'ПОСЛЕ (1 350 оставшихся + %d новых; формула fixS на итоговой копии)' % len(vybor))
t_nov, ch_nov = tablica(prodavec, POSLE, 'ТОЛЬКО НОВЫЕ (%d)' % len(vybor))
t_ub, ch_ub = tablica({i: u['prodavec'] for i, u in UBRAT.items()}, DO, 'УБИРАЕМЫЕ (330, как сейчас)')
PO_RASBROS = {kl: rasbros(POSLE_RASPR, POSLE, f) for kl, _, f in METRIKI + TOLKO_TABLICA}
PO_RASBROS['score'] = rasbros_sr(POSLE_RASPR, POSLE)
DO_RASBROS['mediana'] = DO_RASBROS_MED
PO_RASBROS['mediana'] = {}
for g, chl in enumerate(GRUPPY):
    meds = [E2.mediana([POSLE[i]['vyr'] for i, p in POSLE_RASPR.items() if p == q and not POSLE[i]['rb']]) for q in chl]
    PO_RASBROS['mediana'][g] = max(meds) - min(meds)
HUZHE = {kl: (DO_RASBROS[kl], PO_RASBROS[kl]) for kl in PO_RASBROS if any(PO_RASBROS[kl][g] > DO_RASBROS[kl][g] + 1e-9 for g in (0, 1) if GR_METRIKI.get(kl, g) == g)}
print('перекос (max-min) СЕЙЧАС -> ПОСЛЕ, группа 1–4 / 5–9: %s' % ', '.join('%s %s/%s -> %s/%s' % (
    kl, *(('%.1f' % x) if isinstance(x, float) else x for x in (DO_RASBROS[kl][0], DO_RASBROS[kl][1], PO_RASBROS[kl][0], PO_RASBROS[kl][1])))
    for kl in PO_RASBROS))
print('ХУЖЕ ТЕКУЩЕГО: %s' % (HUZHE or 'нет'))
print(t_do)
print(t_po)
print(t_nov)
for reg, kto in DOM.items():
    chuzh = [i for i, p in POSLE_RASPR.items() if region.get(i) == reg and p not in kto]
    assert not chuzh, (reg, chuzh)
for u, e in edinicy.items():
    assert len({prodavec[i] for i in e['novye']}) == 1
    if e['panel']:
        p0 = sorted({vlad[j] for j in e['panel']})[0]
        assert prodavec[e['novye'][0]] == p0, (u, e)

# ====================================================================== 7. ХОЛДИНГИ В КАТАЛОГ (holding_chlen)
holding_chlen = []
for u, e in edinicy.items():
    vse = e['novye'] + e['panel']
    if len(vse) < 2:
        continue
    gr_panel = None
    for j in ([] if set(e['panel']) & NE_TROGAT else e['panel']):
        g_ = panel[j].get('holding_gruppa')
        if g_ and not g_.startswith('snyato'):
            gr_panel = g_
            break
    gid = gr_panel or ('gQ-' + min(e['novye']))
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
        for j in e['panel']:
            holding_chlen.append({'gruppa': gid, 'inn': j, 'nazvanie': panel[j]['predpriyatie'], 'region': panel[j]['region'],
                                  'segment': panel[j].get('segment'), 'vyruchka_rub': panel[j].get('vyruchka_rub'), 'v_vybore': 1,
                                  'svyaz': '; '.join(sorted(svyazi[j]))[:500]})
print('холдингов (групп 2+ компаний) с новыми: %d, строк holding_chlen %d' % (
    len({h['gruppa'] for h in holding_chlen}), len(holding_chlen)))

# ====================================================================== 8. ПЛАН
kontakty = [dict(x) for i in vybor for x in KESH[i]['kont']]
lyudi = [x for i in vybor for x in KESH[i]['lyud']]
istochniki = [x for i in vybor for x in KESH[i]['ist']]
for i in vybor:
    stat_k.update(KESH[i]['zh'])
for x in kontakty:
    for kk5 in [kk5 for kk5 in x if kk5.startswith('_')]:
        del x[kk5]
verdikty = {}
for i in panel_vse:          # и убираемые – на случай, если по ней появятся действия и её оставят
    v = SVP.get(i)
    if v:
        verdikty[i] = verdikt_polya(dict(v, verdikt_norm=v.get('verdikt')))
for i in vybor:
    verdikty[i] = verdikt_polya(SK[i])
plan = {'vremya': time.strftime('%Y%m%d-%H%M%S'), 'cel': CEL, 'ubrat': UBRAT, 'prodavcy': prodavec, 'dom': DOM, 'fio': FIO,
        'baza': BAZA, 'baza_opisanie': BAZA_OPIS,
        'kompanii': list(kompanii.values()), 'kontakty': kontakty, 'lyudi': lyudi, 'istochniki': istochniki,
        'holding_chlen': holding_chlen, 'novye_kolonki': NOVYE_KOLONKI_COMPANY, 'verdikty': verdikty,
        'stupeni': {i: {'tier': POSLE[i]['tier'], 'score': POSLE[i]['score'], 'ball': POSLE[i]['ball']} for i in vybor},
        'ozhidaemo_vse': {i: {'tier': POSLE[i]['tier'], 'score': POSLE[i]['score']} for i in POSLE},
        'edinicy': {u: e for u, e in edinicy.items() if len(e['novye']) + len(e['panel']) > 1},
        'aktivnye_meyer_inn': sorted(AKT_MEYER | {i for i, (pl, _) in IMENA.items() if pl}),
        'tablica_do': t_do, 'tablica_posle': t_po, 'tablica_novye': t_nov, 'tablica_ubiraemye': t_ub,
        'chisla_do': ch_do, 'chisla_posle': ch_po, 'milp': VAR, 'zapas': ZAPAS,
        'rasbros_do': DO_RASBROS, 'rasbros_posle': PO_RASBROS, 'huzhe_tekushchego': HUZHE,
        'otkaz': otkaz, 'ne_ponadobilis': ne_ponadobilis,
        'svod': {'vzyato': len(vybor), 'godnyh': len(godnye), 'v_ocheredi': len(ochered),
                 'uverennost': dict(collections.Counter(SK[i]['uverennost'] for i in vybor)),
                 'stupen': dict(collections.Counter(E2.STUPEN[POSLE[i]['tier']] for i in vybor)),
                 'rb': sum(POSLE[i]['rb'] for i in vybor), 'bitrix_kusok_7_12': sum(1 for i in vybor if SK[i].get('kusok', 0) >= 7),
                 'vor16': sorted(VOR16 & set(vybor)), 'kontakty': dict(stat_k),
                 'otkaz_po_prichine': dict(collections.Counter(v[0].split(':')[0].split(' (')[0][:60] for v in otkaz.values())),
                 'izm_u_ostavshihsya': [(i, DO[i]['tier'], POSLE[i]['tier'], DO[i]['score'], POSLE[i]['score']) for i in izm_star]}}
io.open(OUT, 'w', encoding='utf-8').write(json.dumps(plan, ensure_ascii=False, indent=0, default=str))
print('итог: взято %d; ступени %s; уверенность %s; Беларусь %d; из кусков 07–12 (Битрикс) %d; номеров %d, людей %d' % (
    len(vybor), plan['svod']['stupen'], plan['svod']['uverennost'], plan['svod']['rb'], plan['svod']['bitrix_kusok_7_12'],
    len(kontakty), len(lyudi)))
print('отказы: %s' % plan['svod']['otkaz_po_prichine'])
print('план: %s (%.0f с)' % (OUT, time.time() - T0))
