# -*- coding: utf-8 -*-
"""Файл 3 Meyer («номера без ролей», подтверждены на живых страницах 06.10) -> JSON для
заливки как «База 3». Формат – как у Баз 6/4/2 (тот же загрузчик).

Владелец 08.10: «из базы 3 отбери в диапазоне 100–1000 млн лучшие компании и догрузи так,
чтобы у каждого было по 150 компаний с равным приоритетом»; раньше – «приоритет не выручка».
Сколько брать – аргумент (сколько не хватает до 150 у всех вместе).

ФИЛЬТР (что не годится вовсе):
  * уже в панели; сегмент только по доп. ОКВЭД; выручка вне 100–1000 млн;
  * описания нет или оно мусорное (агрегатор, каталог, интернет-магазин, сервис проверки
    юрлиц, хостинг, «прилинкуйте домен»);
  * больше 12 номеров на странице (каталог) или нет ни одного своего номера (общий с другими
    ИНН и 8-800 своим не считается).
РЕЙТИНГ «ЛУЧШИХ» – польза для Meyer, а не выручка:
  сегмент для сортировщиков (семеноводы, элеваторы, орехи, ягоды) +10 за каждый, до 30;
  ОКВЭД ядра сортировки (крупы/мука 10.61, овощи-фрукты 10.39, масло 10.41, чай-кофе 10.83,
  специи 10.84, зерно 01.1/46.21/52.10) +10; рентген (мясо, рыба, молоко, готовая еда) +5;
  производство по описанию +10, только торговля −10; НАСТОЯЩИЙ мобильный обязателен (+15),
  рядом с ним «тел/моб/отдел/менеджер…» +5; свой городской +5,
  есть приёмная/общий +3; 1–5 номеров +5; выручка – лишь до +5 (lg).
Балл в очереди (moy_prioritet) – общая шкала баз: выручка, попадание, лучший номер (без ЛПР:
приёмная 5, иначе 0; +5 сайт подтверждён), сегменты.
"""
import collections
import html
import json
import math
import re
import sys

import pandas as pd

VHOD, VYHOD, SKOLKO = sys.argv[1], sys.argv[2], int(sys.argv[3])
PANEL = sys.argv[4:]
x = pd.ExcelFile(VHOD)
K = x.parse('Компании', dtype=str)
N = x.parse('Номера', dtype=str)


def s(v):
    if v is None or (not isinstance(v, str) and pd.isna(v)):
        return ''
    return html.unescape(str(v)).strip()


def chislo(v):
    try:
        f = float(s(v).replace(' ', '').replace(',', '.'))
        return f if f > 0 else None
    except ValueError:
        return None


def cif(v):
    d = re.sub(r'\D', '', re.split(r'доб', s(v), flags=re.I)[0])
    return d[-10:] if len(d) >= 10 else ''


panel, panel_nomera = {}, collections.defaultdict(set)
for p in PANEL:
    d = json.load(open(p, encoding='utf-8'))
    for c in d['kompanii']:
        panel.setdefault(c['inn'], c)
    for xk in d['kontakty']:
        if cif(xk['value']):
            panel_nomera[cif(xk['value'])].add(xk['inn'])

MUSOR = re.compile(r'провер\w* (?:юр|контраг)|егрюл|егрип|прилинкуйте|хостинг|домен (?:продается|продаётся)|'
                   r'beget|reg\.ru|timeweb|справочник|каталог (?:компаний|предприятий|производителей)|агрегатор|'
                   r'сервис проверки|интернет-магазин|маркетплейс|сайт (?:находится|в разработке)', re.I)
HOSTING = re.compile(r'beget|reg\.ru|timeweb|nic\.ru|прилинкуйте|хостинг|tenderguru|rusprofile|checko', re.I)
# Описание должно быть про еду: у части компаний сайт подобран чужой («Фабрика-кухня»: ОКВЭД
# хлебный, а на сайте кухонная мебель; «Премиум продукт»: производство монтажной пены).
EDA = re.compile(r'пищев|продукт\w* питани|мяс|молок|молоч|сыр|хлеб|мук[аиу]|мукомол|круп|зерн|масл|рыб|морепрод|'
                 r'овощ|фрукт|ягод|орех|ч[аа]й|кофе|специ|пряност|приправ|кондитер|конфет|шоколад|напит|сок|м[её]д|'
                 r'семен|элеватор|корм|соус|консерв|полуфабрикат|колбас|птиц|яйц|сахар|сол[ьи]|снек|чипс|морожен|'
                 r'десерт|выпечк|торт|печень|макарон|пельмен|гриб|бакале|сухофрукт|бобов|рис[аоу]?\b|гречк|солод|дрожж', re.I)
NE_EDA = re.compile(r'мебел|монтажн\w* пен|строительн|окна|двер[иь]|запчаст|автомоб|металлопрокат|недвижим|'
                    r'кухни (?:оптом|на заказ)|кухонн\w* гарнитур|косметик|одежд|обув', re.I)
PROIZV = re.compile(r'производ|завод|фабрик|комбинат|цех|выпуска|перерабат|выращива|мельниц|пекарн|маслобо', re.I)
TORG = re.compile(r'торгов|дистрибьют|оптов|поставщик|импорт|реализ', re.I)
YADRO_OKVED = ('10.61', '10.39', '10.41', '10.83', '10.84', '01.1', '46.21', '52.10', '10.62')
RENTGEN_OKVED = ('10.1', '10.20', '10.5', '10.85', '10.86', '10.89')
SORT_SEGM = ('2 семеноводы', '4 элеваторы', '5 орехи', '6 ягоды')

# ПРИНАДЛЕЖНОСТЬ НОМЕРА И САЙТА (владелец: «важно, чтобы номер реально принадлежал этой компании,
# был на её странице, компания правильно определилась, связка сайта и компании была правильной,
# сама база хуже качества»). Три проверки, все обязательны:
#  1) сайт однозначный: один и тот же домен не записан за несколькими ИНН;
#  2) настоящий мобильный стоит на странице ЭТОГО домена (ссылка на источник номера);
#  3) связка сайта и компании подтверждена: ИНН на странице, или отличительное слово из названия
#     (или его латиница, или аббревиатура) есть в описании сайта, во фрагменте страницы или в домене.
OBSHCHIE_SLOVA = {'ООО', 'АО', 'ЗАО', 'ПАО', 'ОАО', 'ИП', 'ТД', 'ТПК', 'ПК', 'НПК', 'НПЦ', 'СПК', 'КФХ', 'ТОРГОВЫЙ', 'ДОМ',
                  'КОМПАНИЯ', 'ГРУППА', 'ПРОИЗВОДСТВЕННАЯ', 'ПРОИЗВОДСТВЕННО', 'ТОРГОВАЯ', 'ТОРГОВО', 'ПРОДУКТ',
                  'ПРОДУКТЫ', 'ПЛЮС', 'АГРО', 'ЗАВОД', 'КОМБИНАТ', 'ФАБРИКА', 'ХОЛДИНГ', 'ФИРМА', 'ПРЕДПРИЯТИЕ',
                  'СЕЛЬСКОХОЗЯЙСТВЕННЫЙ', 'КООПЕРАТИВ', 'ПОТРЕБИТЕЛЬСКИЙ', 'ПЕРЕРАБАТЫВАЮЩИЙ', 'СБЫТОВОЙ',
                  'ОБЩЕСТВО', 'ОГРАНИЧЕННОЙ', 'ОТВЕТСТВЕННОСТЬЮ', 'АКЦИОНЕРНОЕ', 'ЦЕНТР', 'РУС', 'РОССИЯ', 'НОВЫЙ',
                  'ПИЩЕВОЙ', 'ПИЩЕВЫЕ', 'МЯСНОЙ', 'МОЛОЧНЫЙ', 'ХЛЕБ', 'ХЛЕБОЗАВОД', 'МЯСОКОМБИНАТ', 'ЭКО',
                  'АГРОКОМПЛЕКС', 'АГРОКОМБИНАТ', 'АГРОПРОМЫШЛЕННЫЙ', 'КОМПЛЕКС', 'ИНВЕСТ', 'СЕРВИС', 'ТРЕЙД',
                  'ФУД', 'ФУДС', 'ГРУПП', 'СИСТЕМ', 'РЕСУРС', 'СТАНДАРТ', 'КАЧЕСТВО', 'ВКУС', 'ДАР', 'ДАРЫ'}
TRANSLIT = {'а': 'a', 'б': 'b', 'в': 'v', 'г': 'g', 'д': 'd', 'е': 'e', 'ё': 'e', 'ж': 'zh', 'з': 'z', 'и': 'i',
            'й': 'y', 'к': 'k', 'л': 'l', 'м': 'm', 'н': 'n', 'о': 'o', 'п': 'p', 'р': 'r', 'с': 's', 'т': 't',
            'у': 'u', 'ф': 'f', 'х': 'h', 'ц': 'c', 'ч': 'ch', 'ш': 'sh', 'щ': 'sch', 'ъ': '', 'ы': 'y', 'ь': '',
            'э': 'e', 'ю': 'yu', 'я': 'ya'}


def latin(w):
    w = ''.join(TRANSLIT.get(ch, ch) for ch in w.lower())
    return w.replace('kh', 'h').replace('ts', 'c').replace('iy', 'y').replace('yy', 'y')


def domen(url):
    u = s(url).lower()
    u = re.sub(r'^https?://', '', u).split('/')[0].split('?')[0]
    return u[4:] if u.startswith('www.') else u


def slova_nazvaniya(nazv):
    out = []
    for w in re.findall(r'[А-ЯЁA-Z0-9]+', s(nazv).upper()):
        if w in OBSHCHIE_SLOVA or w.isdigit():
            continue
        if len(w) >= 4 or (len(w) >= 3 and w.isalpha() and w == w.upper()):
            out.append(w)
    return out


def svyazka_podtverzhdena(c, ks):
    """Чем подтверждено, что сайт – этой компании (пусто – не подтверждено). Строго:
    название из нескольких слов – в тексте должны быть ВСЕ (или слитно: «ЛюксФуд»); одно слово –
    от 5 букв; домен – слово от 5 букв (кириллицей или латиницей) или аббревиатура целиком."""
    if any('ИНН на странице' in s(r['Чья страница']) for r in ks):
        return 'ИНН на странице'
    slova = slova_nazvaniya(c['Название'])
    if not slova:
        return ''
    tekst = (s(c['Описание']) + ' ' + ' '.join(s(r['Как стоит на странице']) for r in ks)).lower()
    tekst_slitno = re.sub(r'[^а-яёa-z0-9]', '', tekst)
    dom = re.sub(r'[^a-z0-9а-яё]', '', domen(c['Сайт']).rsplit('.', 1)[0])
    for w in slova:
        wl = w.lower()
        if len(w) <= 4:                                   # аббревиатура: ЛЗРМ, СКЗ, ИВКО
            if latin(w) in dom or wl in dom:
                return 'аббревиатура «%s» в домене' % w
        elif wl[:5] in dom or latin(w)[:5] in dom:
            return 'название «%s» в домене' % w.title()
    dlinnye = [w.lower() for w in slova if len(w) >= 5]
    korotkie = [w.lower() for w in slova if len(w) <= 4]
    if ''.join(w.lower() for w in slova) in tekst_slitno and len(''.join(slova)) >= 6:
        return 'название «%s» на сайте' % ' '.join(w.title() for w in slova)
    if dlinnye and all(re.search(r'(?<![а-яё])' + re.escape(w[:5]), tekst) for w in dlinnye) and \
            all(re.search(r'(?<![а-яё])' + re.escape(w) + r'(?![а-яё])', tekst) for w in korotkie):
        return 'название «%s» на сайте' % ' '.join(w.title() for w in slova)
    return ''


inn_na_domen = collections.defaultdict(set)
for _, c in K.iterrows():
    if domen(c['Сайт']):
        inn_na_domen[domen(c['Сайт'])].add(s(c['ИНН']))

nom_po = collections.defaultdict(list)
for _, r in N.iterrows():
    nom_po[s(r['ИНН'])].append(r)
inn_na_nomer = collections.defaultdict(set)
for _, r in N.iterrows():
    if cif(r['Номер']):
        inn_na_nomer[cif(r['Номер'])].add(s(r['ИНН']))


def musor_nomer(r):
    return bool(HOSTING.search(s(r['Как стоит на странице'])))


def svoy(r):
    c = cif(r['Номер'])
    return bool(c) and len(inn_na_nomer[c]) == 1 and not c.startswith('800') and not musor_nomer(r)


# НАСТОЯЩИЙ МОБИЛЬНЫЙ (владелец: «главное, чтобы мобильный номер был настоящий, там она похуже
# качеством»). Разбор файла показал три вида ненастоящих: мини-сайт из справочника («Сайт
# создан в…», «Показать», «Как доехать» – карточка точки, а не сайт компании), страница со
# списком дилеров («Обратиться к дилеру ООО …» – номер дилера), шаблон (+7 903 123-45-67,
# +7 996 000-00-00). Плюс номер, общий у нескольких ИНН, и номер рядом с веб-студией.
MINISAYT = re.compile(r'Сайт создан в|Показать|Как доехать', re.I)
DILER = re.compile(r'дилер|партн[её]р|представител|филиал\w* в', re.I)
STUDIYA = re.compile(r'разработ\w* сайт|создани\w* сайт|сайт (?:сделан|создан)|веб-?студ|продвижени|seo|хостинг|digital', re.I)
ORG = re.compile(r'(?:ООО|АО|ЗАО|ПАО|ОАО|ИП)\s*[«"]\s*([^»"]{2,40})', re.I)


def shablon(c):
    return bool((not c.startswith('9')) or len(set(c)) <= 2 or re.search(r'(\d)\1{5}', c)
                or '1234567' in c or c.endswith('0000000'))


SAYT_INN = {}      # ИНН -> домен сайта компании (заполняется ниже)


def nastoyashchiy_mobilnyy(r):
    if s(r['Тип номера']) != 'мобильный' or not svoy(r):
        return False
    dk = SAYT_INN.get(s(r['ИНН']), '')
    dn = domen(r['Ссылка на источник'])
    if not dk or not (dn == dk or dn.endswith('.' + dk)):
        return False                     # номер не со страницы сайта этой компании
    c = cif(r['Номер'])
    f = s(r['Как стоит на странице'])
    if shablon(c) or MINISAYT.search(f) or DILER.search(f) or STUDIYA.search(f):
        return False
    return len({m.strip().lower() for m in ORG.findall(f)}) <= 1   # на странице не чужие фирмы


for _, c in K.iterrows():
    SAYT_INN[s(c['ИНН'])] = domen(c['Сайт'])
kand, otsev = [], collections.Counter()
for _, c in K.iterrows():
    inn = s(c['ИНН'])
    vyr = chislo(c['Выручка, руб'])
    opis = s(c['Описание'])
    ks = [r for r in nom_po.get(inn, []) if not musor_nomer(r)]
    if inn in panel:
        otsev['уже в панели'] += 1
        continue
    if vyr is None or not (1e8 <= vyr <= 1e9):
        continue
    if s(c['Попадание']) != 'основной ОКВЭД':
        otsev['сегмент только по доп. ОКВЭД'] += 1
    elif not opis or MUSOR.search(opis):
        otsev['нет описания или мусорное'] += 1
    elif not EDA.search(opis) or NE_EDA.search(opis):
        otsev['описание не про еду (чужой сайт)'] += 1
    elif not (1 <= len(ks) <= 12):
        otsev['номеров 0 или больше 12 (каталог)'] += 1
    elif not any(svoy(r) for r in ks):
        otsev['нет своего номера'] += 1
    elif len(inn_na_domen[domen(c['Сайт'])]) > 1:
        otsev['сайт записан за несколькими ИНН'] += 1
    elif not any(nastoyashchiy_mobilnyy(r) for r in ks):
        otsev['нет настоящего мобильного на сайте компании'] += 1
    elif not svyazka_podtverzhdena(c, ks):
        otsev['связка сайта и компании не подтверждена'] += 1
    else:
        segm = [v.strip() for v in s(c['Сегмент']).split('|') if v.strip()]
        okv = s(c['Основной ОКВЭД'])
        b = min(30, 10 * sum(1 for v in segm if v in SORT_SEGM))
        b += 10 if okv.startswith(YADRO_OKVED) else 5 if okv.startswith(RENTGEN_OKVED) else 0
        b += 10 if PROIZV.search(opis) else (-10 if TORG.search(opis) else 0)
        nm = [r for r in ks if nastoyashchiy_mobilnyy(r)]
        b += 15                                      # настоящий мобильный – обязателен, есть у всех
        b += 5 if any(re.search(r'тел|моб|whatsapp|отдел|менеджер|директор|контакт|при[её]мн', s(r['Как стоит на странице']), re.I) for r in nm) else 0
        b += 5 if any(svoy(r) and s(r['Тип номера']) == 'городской' for r in ks) else 0
        b += 3 if any(s(r['Подпись в базе']) == 'общий/приёмная' for r in ks) else 0
        b += 5 if len(ks) <= 5 else 0
        b += max(0.0, min(5.0, 5 * math.log10(vyr / 1e8)))
        kand.append((round(b, 1), c, ks))
print('кандидатов %d; отсев: %s' % (len(kand), dict(otsev)))
kand.sort(key=lambda z: (-z[0], -(chislo(z[1]['Выручка, руб']) or 0), s(z[1]['ИНН'])))
vybor = kand[:SKOLKO]
print('взято %d, рейтинг от %.1f до %.1f (граница: следующий %.1f)' % (
    len(vybor), vybor[0][0], vybor[-1][0], kand[SKOLKO][0] if len(kand) > SKOLKO else 0))


def podgr(v):
    return '100–200' if v < 2e8 else '200–300' if v < 3e8 else '300–500' if v < 5e8 else '500–700' if v < 7e8 else '700–1000'


print('по выручке (млн):', collections.Counter(podgr(chislo(c['Выручка, руб'])) for _, c, _ in vybor).most_common())
print('по сегменту:', collections.Counter(s(c['Сегмент']) for _, c, _ in vybor).most_common(8))
print('ОКВЭД:', collections.Counter(s(c['Основной ОКВЭД'])[:5] for _, c, _ in vybor).most_common(12))
print('с настоящим мобильным:', sum(1 for _, _, ks in vybor if any(nastoyashchiy_mobilnyy(r) for r in ks)))

# группы: общий номер с другой компанией (файла 3 из отобранных или панели); gid g3-
roditel = {}


def koren(a):
    roditel.setdefault(a, a)
    while roditel[a] != a:
        roditel[a] = roditel[roditel[a]]
        a = roditel[a]
    return a


vybrannye = {s(c['ИНН']) for _, c, _ in vybor}
obshchih = collections.Counter()
for k10, inns in inn_na_nomer.items():
    vse = sorted((set(inns) & vybrannye) | panel_nomera.get(k10, set()))
    if len(vse) > 1 and len(set(inns) | panel_nomera.get(k10, set())) <= 4:
        for i in vse:
            obshchih[i] += 1
        for i in vse[1:]:
            roditel[koren(i)] = koren(vse[0])
kf = {s(c['ИНН']): c for _, c, _ in vybor}
gr = collections.defaultdict(list)
for i in set(roditel):
    gr[koren(i)].append(i)
gruppy = {}
for g, chl in gr.items():
    if len(chl) < 2 or not any(i in vybrannye for i in chl):
        continue
    sp = []
    for i in chl:
        c = kf.get(i)
        sp.append({'inn': i, 'nazvanie': s(c['Название']) if c is not None else panel[i]['predpriyatie'],
                   'region': s(c['Регион']) if c is not None else panel[i]['region'],
                   'segment': s(c['Сегмент']) if c is not None else panel[i]['segment'],
                   'vyruchka_rub': chislo(c['Выручка, руб']) if c is not None else panel[i].get('vyruchka_rub'),
                   'v_vybore': True, 'svyaz': 'общих номеров на сайтах компаний: %d' % obshchih[i]})
    gruppy['g3-' + min(chl)] = {'nazvanie': '', 'chleny': sorted(sp, key=lambda z: -(z['vyruchka_rub'] or 0))}
gruppa_inn = {ch['inn']: gid for gid, g in gruppy.items() for ch in g['chleny'] if ch['inn'] in vybrannye}
print('групп: %d %s' % (len(gruppy), [[ch['nazvanie'][:22] for ch in g['chleny']] for g in gruppy.values()]))

kompanii, kontakty = [], []
for reyt, c, ks in vybor:
    inn = s(c['ИНН'])
    vyr = chislo(c['Выручка, руб'])
    segm = [v.strip() for v in s(c['Сегмент']).split('|') if v.strip()]
    est_kom = any(s(r['Подпись в базе']) == 'общий/приёмная' for r in ks)
    b_vyr = max(0.0, min(40.0, 10 * math.log10(vyr / 1e7)))
    b_kont = (5 if est_kom else 0) + 5      # без ЛПР: приёмная 5; сайт подтверждён (страница своя) +5
    b_segm = min(15, 5 * max(0, len(segm) - 1))
    ball = round(b_vyr + 20 + b_kont + b_segm, 1)
    luchshiy = next(r for r in ks if nastoyashchiy_mobilnyy(r))
    okv = s(c['Основной ОКВЭД'])
    dop = [v.strip() for v in s(c['Доп. ОКВЭД']).split(',') if v.strip()]
    god = s(c['Год выручки'])
    kompanii.append({
        'inn': inn, 'sliyanie': False, 'predpriyatie': s(c['Название']), 'region': s(c['Регион']),
        'sayt': s(c['Сайт']), 'okved': okv, 'okvedy_vse': ' | '.join([okv] + [d for d in dop if d != okv]),
        'opisanie': s(c['Описание']), 'produkciya': '', 'moshchnosti': '',
        'vyruchka_rub': vyr, 'fin_god': god[:-2] if god.endswith('.0') else god,
        'segment': ' | '.join(segm), 'segment_osn': s(c['Сегмент по основному ОКВЭД']), 'popadanie': 'основной ОКВЭД',
        'v_baze_obzvona': s(c['В какой базе обзвона']),
        'lpr_kratko': 'ЛПР не найден, мобильный с сайта: %s' % s(luchshiy['Номер']),
        'lpr_roli': '', 'moy_prioritet': ball,
        'prioritet_pochemu': 'выручка %+.0f · попадание +20 · лучший номер %+d · сегменты %+d = %.1f; '
                             'отбор в Базу 3: рейтинг пользы %.1f' % (b_vyr, b_kont, b_segm, ball, reyt),
        'kachestvo_nomera': 'без ролей: настоящий мобильный',
        'n_phones': len(ks), 'has_phone': 1, 'n_purchaser': 0, 'n_tech': 0, 'lpr_mobilnyy': 0, 'lpr_s_fio': 0,
        'bitrix_fajl': '', 'holding': '', 'holding_gruppa': gruppa_inn.get(inn, ''), 'v_fajlah_meyer': 'файл 3',
        'razdel_kc': '', 'sayt_chey': 'связка сайта и компании: ' + svyazka_podtverzhdena(c, ks), 'otkuda_kompaniya': '',
        'ssylki_na_istochniki': ' | '.join(sorted({s(r['Ссылка на источник']) for r in ks if s(r['Ссылка на источник'])})),
    })
    for r in ks:
        podp = s(r['Подпись в базе'])
        nast = nastoyashchiy_mobilnyy(r)
        naverh = nast or podp == 'общий/приёмная'
        kontakty.append({
            'inn': inn, 'value': s(r['Номер']), 'kind': 'phone', 'person': None, 'role': podp,
            'position': 'мобильный с сайта, без подписи' if nast and not podp else '',
            'phone_type': 'мобильный' if s(r['Тип номера']) == 'мобильный' else 'рабочий',
            'source': ' · '.join(v for v in (s(r['Источник']), s(r['Чья страница']), 'номер на живой странице 06.10',
                                             'номер общий у нескольких компаний' if not svoy(r) else '') if v),
            'source_url': s(r['Ссылка на источник']) or None, 'fragment': s(r['Как стоит на странице'])[:400],
            'is_purchaser': 0, 'is_tech': 0, 'has_role': int(naverh),
            'nomer_ne_lichnyy': None if naverh else (podp or ('без подписи' if svoy(r) else 'общий у нескольких компаний')),
            'lpr': 0, 'cifry': cif(r['Номер']),
        })
json.dump({'kompanii': kompanii, 'kontakty': kontakty, 'gruppy': gruppy, 'lyudi': [],
           'fajl': '3-meyer-nomera-bez-roley-0710_1.xlsx', 'baza': 'База 3',
           'baza_opisanie': 'номера без ролей'},
          open(VYHOD, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
print('компаний %d, номеров %d -> %s' % (len(kompanii), len(kontakty), VYHOD))
print('верх:')
for reyt, c, ks in vybor[:15]:
    print('   %5.1f %-30s %-6s %-26s | %s' % (reyt, s(c['Название'])[:30], s(c['Основной ОКВЭД']), domen(c['Сайт'])[:26], svyazka_podtverzhdena(c, ks)[:40]))
import random
print('случайные 10 из взятых:')
for reyt, c, ks in random.Random(7).sample(vybor, min(12, len(vybor))):
    print('   %5.1f %-30s %-22s %-36s | %s' % (reyt, s(c['Название'])[:30], domen(c['Сайт'])[:22], svyazka_podtverzhdena(c, ks)[:36], s(c['Описание'])[:40]))
