# -*- coding: utf-8 -*-
r"""Исправитель E1 панели Meyer (08.10.2026): регионы, часовые пояса, сегменты, пометки компаний.

Пишет ТОЛЬКО в таблицу company каталога C:\centro2\data\meyer_baza1.db и только свои колонки:
region, region_ishodnyy, chas_poyas, chas_poyas_kak, segment, segment_ishodnyy, segment_osn,
popadanie и новые: region_istochnik, segment_dop, segment_osn_ishodnyy, popadanie_ishodnoe,
pometka_ocheredi, bitrix_klient_sc, bitrix_sdelok. Код панели не трогает (замок не нужен).

1. РЕГИОН = субъект юрадреса (adres, залит из checko) тем же приведением к официальному
   названию, что в panel_segmenty_regiony.py. Пустой регион, село вместо субъекта, другой
   субъект – исправляются; прежнее значение остаётся в region_ishodnyy (если там пусто).
   Без юрадреса – ручные правки с доказательством (ИП Летуновский: адрес производства на
   сайте и код региона в ИНН – Тамбовская область). Пояс пересчитывается по новому региону.
   Источник региона накапливается в region_istochnik (файл базы | юрадрес checko | сайт).
2. СЕГМЕНТ = по ОСНОВНОМУ ОКВЭД через таблицу okved_segment_tz.json (та же, что в прошлой
   правке; вне таблицы – самое длинное совпадающее начало кода, иначе 10/11/46.3 – «3 пищевые»).
   Сегменты по дополнительным ОКВЭД и прежние сегменты файлов, не подтверждённые основным
   кодом, – в segment_dop. segment_osn = тот же сегмент; popadanie = «основной ОКВЭД», если
   основной код дал сегмент, иначе «только доп. ОКВЭД». Прежние значения – в *_ishodnyy/_ishodnoe.
3. pometka_ocheredi = «нецелевая: <ОКВЭД, название>» – основной ОКВЭД не пищевая/агро
   переработка (розница 47, нефтепродукты 19, стройка 41–43, транспорт 49–53, добыча, услуги
   в растениеводстве 01.61…). Не помечаются: всё, что даёт сегмент по таблице, 01.1–01.5
   (растениеводство/животноводство), 03 (рыба), 46.17/46.21/46.23 и 46.3 (опт сырья и продуктов).
4. pometka_ocheredi = «недействующая: …» по status_egrul: ликвидирована, в процессе
   ликвидации, к исключению из ЕГРЮЛ. Реорганизация, смена адреса, уменьшение капитала – нет.
5. bitrix_sdelok – число сделок из bitrix_kc_info; bitrix_klient_sc = 1, если есть сделки в
   воронках «СЦ -» (продажа/сопровождение/гарантия/ПНР) – действующий клиент сервисного центра.

Перед записью – копия каталога (backup API) в C:\centro2\_bekap\fixE1-<время>\ (назад целиком
НЕ возвращается). Журнал «было -> стало» по каждой ячейке – на дроп fixE1_zhurnal_<время>.json.
Проверка – отдельным venv-процессом, TestClient на ВРЕМЕННОЙ копии базы продаж; провал –
откат по своему журналу (только ячейки, которые всё ещё равны «стало»).

    python3 zapusk_na_servere.py fixE1_regiony_segmenty.py --suhoy     # план без записи
    python3 zapusk_na_servere.py fixE1_regiony_segmenty.py             # запись + проверка
    python3 zapusk_na_servere.py fixE1_regiony_segmenty.py --proverka  # только проверка
    python3 zapusk_na_servere.py fixE1_regiony_segmenty.py --otkat fixE1_zhurnal_<время>.json
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
PUT = '/obzvon-meyer'

# таблица «основной ОКВЭД -> сегмент» – копия seo-texts/okved_segment_tz.json (61 код из файлов Баз 2–4)
OKVED_TZ = json.loads(r'''{"10.41":"3 пищевые","10.61":"3 пищевые | 4 элеваторы","10.39":"3 пищевые","10.41.54":"3 пищевые","01.11.1":"2 семеноводы","10.11":"3 пищевые","10.32":"3 пищевые | 6 ягоды","52.10.3":"4 элеваторы","10.51":"3 пищевые","10.13":"3 пищевые","01.63":"4 элеваторы","10.31":"3 пищевые","01.64":"2 семеноводы","10.71":"3 пищевые","10.83":"3 пищевые","10.89":"3 пищевые","10.81":"3 пищевые","10.2":"3 пищевые","10.52":"3 пищевые","10.72":"3 пищевые","10.85":"3 пищевые","10.20":"3 пищевые","10.84":"3 пищевые","10.82":"3 пищевые","10.12":"3 пищевые","10.62":"3 пищевые","10.86":"3 пищевые","01.11":"2 семеноводы","10.20.1":"3 пищевые","10.71.1":"3 пищевые","10.86.2":"3 пищевые","10.51.3":"3 пищевые","10.13.2":"3 пищевые","10.72.1":"3 пищевые","10.51.9":"3 пищевые","10.42":"3 пищевые","10.51.2":"3 пищевые","10.11.1":"3 пищевые","10.51.1":"3 пищевые","10.72.31":"3 пищевые","10.73":"3 пищевые","10.86.7":"3 пищевые","10.89.9":"3 пищевые","10.91.1":"3 пищевые","10.13.4":"3 пищевые","10.73.3":"3 пищевые","10.41.24":"3 пищевые","10.72.2":"3 пищевые","10.13.1":"3 пищевые","10.61.2":"3 пищевые | 4 элеваторы","10.91.3":"3 пищевые","10.82.2":"3 пищевые","10.41.4":"3 пищевые","10.41.5":"3 пищевые","10.62.1":"3 пищевые","10.92":"3 пищевые","10.91":"3 пищевые","01.25.1":"6 ягоды","10.72.32":"3 пищевые","10.86.6":"3 пищевые","01.11.3":"2 семеноводы"}''')

# ---------------------------------------------------------------- регионы и пояса (как в panel_segmenty_regiony.py)
REGIONY = [  # (регулярка по нижнему регистру, официальное название) – порядок важен
    (r'санкт|петербург', 'Санкт-Петербург'), (r'севастопол', 'Севастополь'),
    (r'(?<![а-яё])москв', 'Москва'), (r'московск', 'Московская область'),
    (r'ленинградск', 'Ленинградская область'),
    (r'ханты|югра|нижневартовск|сургут', 'Ханты-Мансийский автономный округ – Югра'),
    (r'ямало', 'Ямало-Ненецкий автономный округ'), (r'ненецк', 'Ненецкий автономный округ'),
    (r'чукот', 'Чукотский автономный округ'), (r'еврейск', 'Еврейская автономная область'),
    (r'республика алтай|респ\w*\.? алтай|алтай респ', 'Республика Алтай'), (r'алтайск', 'Алтайский край'),
    (r'адыге', 'Республика Адыгея'), (r'башкор|(?<![а-яё])уфа', 'Республика Башкортостан'),
    (r'бурят', 'Республика Бурятия'), (r'дагестан', 'Республика Дагестан'), (r'ингуш', 'Республика Ингушетия'),
    (r'кабардин', 'Кабардино-Балкарская Республика'), (r'калмык', 'Республика Калмыкия'),
    (r'карачаев', 'Карачаево-Черкесская Республика'), (r'карел|рауталахти', 'Республика Карелия'),
    (r'(?<![а-яё])коми(?![а-яё])', 'Республика Коми'), (r'крым', 'Республика Крым'),
    (r'марий', 'Республика Марий Эл'), (r'мордов', 'Республика Мордовия'),
    (r'сахалин', 'Сахалинская область'), (r'саха|якут', 'Республика Саха (Якутия)'),
    (r'осетия', 'Республика Северная Осетия – Алания'), (r'татарстан|казань|мамадыш', 'Республика Татарстан'),
    (r'(?<![а-яё])тыва|(?<![а-яё])тува', 'Республика Тыва'), (r'удмурт|ижевск', 'Удмуртская Республика'),
    (r'хакас', 'Республика Хакасия'), (r'чечен|мескер', 'Чеченская Республика'),
    (r'чуваш|чебоксар|пархикас', 'Чувашская Республика'),
    (r'донецк', 'Донецкая Народная Республика'), (r'луганск', 'Луганская Народная Республика'),
    (r'забайкал|(?<![а-яё])чита', 'Забайкальский край'), (r'камчат', 'Камчатский край'),
    (r'краснодар|кубан', 'Краснодарский край'), (r'краснояр', 'Красноярский край'),
    (r'(?<![а-яё])перм', 'Пермский край'), (r'примор|владивосток', 'Приморский край'),
    (r'ставропол', 'Ставропольский край'), (r'хабаров', 'Хабаровский край'),
    (r'амурск', 'Амурская область'), (r'архангел', 'Архангельская область'), (r'астрахан', 'Астраханская область'),
    (r'белгород', 'Белгородская область'), (r'брянск', 'Брянская область'), (r'владимир', 'Владимирская область'),
    (r'волгоград', 'Волгоградская область'), (r'вологод|череповец', 'Вологодская область'),
    (r'воронеж', 'Воронежская область'), (r'запорож', 'Запорожская область'), (r'иванов', 'Ивановская область'),
    (r'иркут', 'Иркутская область'), (r'калининград', 'Калининградская область'),
    (r'калуж|кондрово', 'Калужская область'), (r'кемеров|кузбас', 'Кемеровская область – Кузбасс'),
    (r'(?<![а-яё])киров', 'Кировская область'), (r'костром', 'Костромская область'), (r'курган', 'Курганская область'),
    (r'(?<![а-яё])курск', 'Курская область'), (r'липец', 'Липецкая область'), (r'магадан', 'Магаданская область'),
    (r'мурман', 'Мурманская область'), (r'нижегород|нижн\w* новгород', 'Нижегородская область'),
    (r'новгород', 'Новгородская область'), (r'новосиб', 'Новосибирская область'),
    (r'(?<![а-яё])омск', 'Омская область'), (r'оренбург', 'Оренбургская область'),
    (r'орловск|(?<![а-яё])ор[её]л(?![а-яё])', 'Орловская область'), (r'пенз|сурск', 'Пензенская область'),
    (r'псков', 'Псковская область'), (r'ростов', 'Ростовская область'), (r'рязан', 'Рязанская область'),
    (r'самар', 'Самарская область'), (r'саратов', 'Саратовская область'),
    (r'свердлов|екатеринбург', 'Свердловская область'), (r'смолен', 'Смоленская область'),
    (r'тамбов', 'Тамбовская область'), (r'твер|старица', 'Тверская область'),
    (r'(?<![а-яё])томск', 'Томская область'), (r'(?<![а-яё])туль|(?<![а-яё])тула(?![а-яё])', 'Тульская область'),
    (r'тюмен', 'Тюменская область'), (r'ульянов', 'Ульяновская область'), (r'херсон', 'Херсонская область'),
    (r'челябин', 'Челябинская область'), (r'ярослав', 'Ярославская область'),
]
OFICIALNYE = {imya for _, imya in REGIONY}

POYASA = [
    (2, ('калининград',)), (12, ('камчат', 'чукот')), (11, ('магадан', 'сахалин')),
    (10, ('хабаровск', 'приморск', 'владивосток', 'еврейск')),
    (9, ('забайкаль', 'чита', 'читин', 'амурск', 'якут', 'саха (')), (8, ('иркут', 'бурят')),
    (7, ('новосиб', 'томск', 'кемеров', 'кузбас', 'алтай', 'краснояр', 'хакас', 'тыва')), (6, ('омск',)),
    (5, ('башкорт', 'уфа', 'оренбург', 'перм', 'свердлов', 'екатеринбург', 'челябин', 'курган',
         'тюмен', 'ханты', 'югра', 'ямал')),
    (4, ('самар', 'саратов', 'ульянов', 'астрахан', 'удмурт', 'ижевск')),
]

# Без юрадреса в checko (ИП): регион по доказательству, проверено 08.10 на живом сайте
RUCHNYE_REGIONY = {
    '682708704703': ('Тамбовская область',
                     'сайт mkletunovsky.ru/contacts: «Тамбовская обл., Мичуринский р-н, пос. Зеленый Гай» '
                     '| код региона в ИНН 68 (Тамбовская область)'),
}


def s_nachala(slovo, tekst):
    return re.search(r'(?<![а-яё])' + re.escape(slovo), tekst) is not None


def poyas(region):
    r = (region or '').casefold()
    for smeshch, slova in POYASA:
        if any(s_nachala(sl, r) for sl in slova):
            return smeshch, 'по региону'
    if not r:
        return 3, 'по Москве: регион не указан'
    if any(re.search(rx, r) for rx, _ in REGIONY):
        return 3, 'по региону'
    return 3, 'по Москве: регион не распознан'


def region_norm(raw):
    r = (raw or '').strip().lower()
    if not r:
        return ''
    for rx, imya in REGIONY:
        if re.search(rx, r):
            return imya
    return (raw or '').strip()


def subekt_adresa(adres):
    """Субъект РФ из юрадреса checko: «394026, Воронежская область, г. Воронеж, …» -> официальное название.
    Берётся ТОЛЬКО часть адреса после индекса (в остальном адресе бывают «пр-кт Московский» и т. п.)."""
    chasti = [p.strip() for p in (adres or '').split(',') if p.strip()]
    if chasti and re.match(r'^\d{6}$', chasti[0]):
        chasti = chasti[1:]
    if not chasti:
        return '', ''
    syroy = chasti[0]
    imya = region_norm(syroy)
    return (imya if imya in OFICIALNYE else ''), syroy


# ---------------------------------------------------------------- сегменты
def po_kodu(kod, tablica):
    kod = (kod or '').strip()
    luchshiy = ''
    for nachalo in tablica:
        if (kod == nachalo or kod.startswith(nachalo + '.') or (len(nachalo) <= 2 and kod.startswith(nachalo))) \
                and len(nachalo) > len(luchshiy):
            luchshiy = nachalo
    return luchshiy


def segment_tz(kod):
    k = po_kodu(kod, OKVED_TZ)
    if k:
        return OKVED_TZ[k]
    if re.match(r'(10|11)\.|46\.3', kod or ''):
        return '3 пищевые'
    return ''


TZ = re.compile(r'^\d ')


def segs(s):
    return [x.strip() for x in str(s or '').split('|') if x.strip()]


def tz_chasti(s):
    return [x for x in segs(s) if TZ.match(x) and 'доп. ОКВЭД' not in x]


def poryadok(spisok):
    return sorted(set(spisok), key=lambda x: (int(x.split()[0]) if x[:1].isdigit() else 99, x))


# ---------------------------------------------------------------- нецелевые по основному ОКВЭД
CELEVYE_NACHALA = (r'01\.[1-5]', r'03\.', r'46\.17', r'46\.21', r'46\.23', r'46\.3')
NAZVANIYA_OKVED = {
    '01.61': 'предоставление услуг в области растениеводства',
    '01.62': 'предоставление услуг в области животноводства',
    '08.11': 'добыча декоративного и строительного камня, известняка, гипса, мела и сланцев',
    '19.20': 'производство нефтепродуктов',
    '42.11': 'строительство автомобильных дорог и автомагистралей',
    '47.11': 'торговля розничная преимущественно пищевыми продуктами, включая напитки, и табачными '
             'изделиями в неспециализированных магазинах',
    '47.76.1': 'торговля розничная цветами и другими растениями, семенами и удобрениями в специализированных магазинах',
    '52.24.2': 'транспортная обработка прочих грузов',
}
RAZDELY = [  # запасные названия по началу кода, если кода нет в словаре
    (r'0[5-9]\.', 'добыча полезных ископаемых'), (r'19\.', 'производство кокса и нефтепродуктов'),
    (r'4[1-3]\.', 'строительство'), (r'45\.', 'торговля и ремонт автотранспорта'), (r'47\.', 'розничная торговля'),
    (r'4[9]\.|5[0-3]\.', 'транспорт, складское хозяйство, логистика'), (r'01\.6', 'услуги в сельском хозяйстве'),
]


def necelevaya(kod):
    """'' – целевая; иначе текст пометки «нецелевая: <код>, <название>»."""
    kod = (kod or '').strip()
    if not kod or segment_tz(kod):
        return ''
    if any(re.match(n, kod) for n in CELEVYE_NACHALA):
        return ''
    imya = NAZVANIYA_OKVED.get(kod) or next((t for rx, t in RAZDELY if re.match(rx, kod)), 'не пищевая и не агро переработка')
    return 'нецелевая: %s, %s' % (kod, imya)


def nedeystvuyushchaya(status):
    s = (status or '').strip()
    nz = s.casefold()
    if not s or 'действующ' in nz and 'недейств' not in nz:
        return ''
    if 'ликвидирован' in nz:
        m = re.search(r'ликвидировано?\s+(\d{1,2}\s+\S+\s+\d{4})', s)
        pp = re.search(r'правопреемник\s+(.+)$', s)
        return 'недействующая: ликвидирована%s%s' % ((' ' + m.group(1)) if m else '',
                                                    ('; правопреемник ' + pp.group(1).strip()) if pp else '')
    if 'ликвидац' in nz:
        return 'недействующая: в процессе ликвидации (%s)' % s[:120]
    if 'исключени' in nz and 'егрюл' in nz:
        m = re.search(r'с (\d{1,2} \S+ \d{4})', s)
        return 'недействующая: к исключению из ЕГРЮЛ%s%s' % (
            (' с ' + m.group(1)) if m else '', ' (запись о недостоверности сведений)' if 'недостоверн' in nz else '')
    if 'прекратил' in nz or 'недейств' in nz:
        return 'недействующая: %s' % s[:150]
    return ''      # реорганизация, смена адреса, уменьшение капитала – компания работает


def bitrix(info):
    m = re.match(r'\s*сделок\s+(\d+)\s*:\s*(.*)$', info or '')
    if not m:
        return None, 0, ''
    voronki = {}
    for chast in m.group(2).split(','):
        mm = re.match(r'\s*(.+?)\s*×\s*(\d+)\s*$', chast)
        if mm:
            voronki[mm.group(1)] = voronki.get(mm.group(1), 0) + int(mm.group(2))
    sc = {v: n for v, n in voronki.items() if re.match(r'СЦ\s*[-–—]', v)}
    return int(m.group(1)), (1 if sc else 0), ', '.join('%s ×%d' % x for x in sc.items())


MOI_POMETKI = re.compile(r'^(нецелевая|недействующая):')


# ---------------------------------------------------------------- план (общая часть: сервер и локальная проверка)
def plan(rows):
    """rows – список dict строк company. Возвращает [(inn, {kolonka: novoe}, {kolonka: pochemu})], счётчики."""
    izm, sch = [], {}

    def plus(k, n=1):
        sch[k] = sch.get(k, 0) + n
    for c in rows:
        inn = c['inn']
        n, poch = {}, {}
        # ---------------- 1. регион
        reg = (c.get('region') or '').strip()
        sub, syroy = subekt_adresa(c.get('adres'))
        if inn in RUCHNYE_REGIONY:
            nov, ist = RUCHNYE_REGIONY[inn]
            vid = 'другой субъект по сайту и коду ИНН (юрадреса в checko нет)'
        elif sub:
            nov = sub
            ist = 'юрадрес checko.ru' if nov != reg else 'файл базы | юрадрес checko.ru'
            vid = ('пустой -> субъект юрадреса' if not reg else
                   'село/город -> субъект юрадреса' if reg not in OFICIALNYE else 'другой субъект -> субъект юрадреса')
        else:
            nov, ist, vid = reg, ('файл базы (юрадреса в checko нет)' if reg else ''), ''
            if syroy:
                plus('регион: субъект юрадреса не распознан')
        if nov != reg:
            n['region'] = nov
            poch['region'] = '%s (юрадрес: %s)' % (vid, (c.get('adres') or '–')[:90])
            plus('регион: ' + vid)
            if not (c.get('region_ishodnyy') or '').strip() and reg:
                n['region_ishodnyy'] = reg
        if nov == reg and (c.get('region_istochnik') or '').strip():
            ist = c['region_istochnik']          # повторный прогон: уже записанный источник не переписывать
        if ist and (c.get('region_istochnik') or '') != ist:
            n['region_istochnik'] = ist
        sm, kak = poyas(nov)
        try:
            star = int(c.get('chas_poyas'))
        except (TypeError, ValueError):
            star = None
        if star != sm:
            n['chas_poyas'] = sm
            poch['chas_poyas'] = 'UTC+%s -> UTC+%d по региону «%s»' % (star, sm, nov)
            plus('пояс: изменилось смещение')
        if (c.get('chas_poyas_kak') or '') != kak:
            n['chas_poyas_kak'] = kak
            plus('пояс: изменилось «как определён»')
        # ---------------- 2. сегмент по основному ОКВЭД
        okv = (c.get('okved') or '').strip()
        osn = segs(segment_tz(okv))
        seg_nov = ' | '.join(osn)
        dop_kody = [k for k in segs(c.get('okvedy_vse')) if k != okv]
        iz_dop = [s for k in dop_kody for s in segs(segment_tz(k))]
        prezhnie = tz_chasti(c.get('segment')) + tz_chasti(c.get('segment_osn')) + \
            tz_chasti(c.get('segment_ishodnyy')) + tz_chasti(c.get('segment_dop'))
        dop_nov = ' | '.join(poryadok([s for s in iz_dop + prezhnie if s not in osn]))
        if (c.get('segment') or '') != seg_nov:
            n['segment'] = seg_nov
            poch['segment'] = 'по основному ОКВЭД %s; прежние сверх основного -> segment_dop' % okv
            plus('сегмент: изменён на сегмент основного ОКВЭД')
            if not (c.get('segment_ishodnyy') or '').strip():
                n['segment_ishodnyy'] = c.get('segment') or ''
        if (c.get('segment_osn') or '') != seg_nov:
            n['segment_osn'] = seg_nov
            if not (c.get('segment_osn_ishodnyy') or '').strip():
                n['segment_osn_ishodnyy'] = c.get('segment_osn') or ''
            plus('segment_osn: выровнен')
        if (c.get('segment_dop') or '') != dop_nov:
            n['segment_dop'] = dop_nov
        pop = 'основной ОКВЭД' if osn else 'только доп. ОКВЭД'
        if (c.get('popadanie') or '') != pop:
            n['popadanie'] = pop
            poch['popadanie'] = 'основной ОКВЭД %s %s' % (okv, 'даёт сегмент %s' % seg_nov if osn else 'не даёт сегмента по таблице')
            plus('попадание: %s -> %s' % (c.get('popadanie') or '–', pop))
            if not (c.get('popadanie_ishodnoe') or '').strip():
                n['popadanie_ishodnoe'] = c.get('popadanie') or ''
        # ---------------- 3–4. пометки очереди
        moi = [x for x in (necelevaya(okv), nedeystvuyushchaya(c.get('status_egrul'))) if x]
        chuzhie = [x.strip() for x in str(c.get('pometka_ocheredi') or '').split(' | ')
                   if x.strip() and not MOI_POMETKI.match(x.strip())]
        pom = ' | '.join(moi + chuzhie)
        if (c.get('pometka_ocheredi') or '') != pom:
            n['pometka_ocheredi'] = pom
            poch['pometka_ocheredi'] = 'основной ОКВЭД %s; статус ЕГРЮЛ: %s' % (okv, (c.get('status_egrul') or '–')[:80])
        for x in moi:
            plus('пометка: ' + x.split(':')[0])
        # ---------------- 5. Битрикс
        chislo, klient_sc, _ = bitrix(c.get('bitrix_kc_info'))
        if chislo is None:
            try:
                chislo = int(c.get('bitrix_kc') or 0)
            except (TypeError, ValueError):
                chislo = 0
        if c.get('bitrix_sdelok') != chislo:
            n['bitrix_sdelok'] = chislo
        if c.get('bitrix_klient_sc') != klient_sc:
            n['bitrix_klient_sc'] = klient_sc
        if klient_sc:
            plus('битрикс: клиент СЦ')
        if n:
            izm.append((inn, n, poch))
    return izm, sch


NOVYE_KOLONKI = (('region_istochnik', 'TEXT'), ('segment_dop', 'TEXT'), ('segment_osn_ishodnyy', 'TEXT'),
                 ('popadanie_ishodnoe', 'TEXT'), ('pometka_ocheredi', 'TEXT'),
                 ('bitrix_klient_sc', 'INTEGER'), ('bitrix_sdelok', 'INTEGER'))
MOI_KOLONKI = ('region', 'region_ishodnyy', 'region_istochnik', 'chas_poyas', 'chas_poyas_kak', 'segment',
               'segment_ishodnyy', 'segment_osn', 'segment_osn_ishodnyy', 'segment_dop', 'popadanie',
               'popadanie_ishodnoe', 'pometka_ocheredi', 'bitrix_klient_sc', 'bitrix_sdelok')


def schyot_segmentov(rows):
    sch = {}
    for c in rows:
        for s in segs(c.get('segment')):
            sch[s] = sch.get(s, 0) + 1
    return dict(sorted(sch.items())), sum(sch.values()), sum(1 for c in rows if segs(c.get('segment')))


def povtor(f, *a):
    for i in range(12):
        try:
            return f(*a)
        except sqlite3.OperationalError as e:
            if 'locked' not in str(e) and 'busy' not in str(e):
                raise
            print('   база занята, повтор через 5 с (%d)' % (i + 1))
            time.sleep(5)
    raise SystemExit('база занята слишком долго')


# ====================================================================== ПРОВЕРКА (venv, TestClient)
if '--proverka' in sys.argv and os.path.normcase(sys.executable) != os.path.normcase(VENV) and os.path.exists(VENV):
    # отдельный запуск проверки системным питоном: fastapi/TestClient есть только в venv
    r = subprocess.run([VENV, os.path.abspath(__file__)] + sys.argv[1:], capture_output=True, timeout=1200, cwd=KOREN,
                       env=dict(os.environ, PYTHONIOENCODING='utf-8'))
    sys.stdout.write(r.stdout.decode('utf-8', 'replace')[-5000:])
    sys.stdout.write(r.stderr.decode('utf-8', 'replace')[-1500:] if r.returncode else '')
    raise SystemExit(r.returncode)
if '--proverka' in sys.argv:
    sys.path.insert(0, KOREN)
    import zapusk  # noqa: F401
    import collections
    import logging
    import warnings
    warnings.filterwarnings('ignore')
    logging.disable(logging.CRITICAL)
    # главная назначает новые ИНН – пусть пишет во ВРЕМЕННУЮ копию базы продаж, а не в живую
    for f in os.listdir(os.path.join(KOREN, '_bekap')):     # копии от прерванных прошлых проверок
        if f.startswith('fixE1-proverka-') and f.endswith('.db'):
            try:
                os.remove(os.path.join(KOREN, '_bekap', f))
            except OSError:
                pass
    TEST_DB = os.path.join(KOREN, '_bekap', 'fixE1-proverka-%s.db' % os.getpid())
    src = sqlite3.connect(os.environ['CENTRO_SALES_DB'])
    dst = sqlite3.connect(TEST_DB)
    src.backup(dst)
    src.close()
    dst.close()
    os.environ['CENTRO_SALES_DB'] = TEST_DB
    os.environ['PARK_OCHERED_SALES_DB'] = TEST_DB
    from app.api import routes_centro_sales as rcs
    from app.obzvon import create_app
    from fastapi.testclient import TestClient
    plohih = 0

    def proverit(u, t):
        global plohih
        if not u:
            plohih += 1
        print('   %s %s' % ('ОК ' if u else 'ПЛОХО', t))

    def myagko(u, t):
        # вид страницы могут менять другие агенты: не найденная разметка – предупреждение, а не откат данных
        print('   %s %s' % ('ОК ' if u else 'ВНИМАНИЕ (разметка не найдена/изменилась)', t))

    k = sqlite3.connect('file:%s?mode=ro' % KAT, uri=True)
    k.row_factory = sqlite3.Row
    rows = [dict(r) for r in k.execute('select * from company')]
    po_inn = {r['inn']: r for r in rows}
    ostatok, _ = plan(rows)
    proverit(not ostatok, 'повторный план пуст (правка идемпотентна): %d' % len(ostatok))
    neof = sorted({r['region'] for r in rows if (r['region'] or '') not in OFICIALNYE})
    proverit(not neof, 'все регионы – официальные субъекты; вне списка: %s' % neof)
    proverit(not [r for r in rows if r['chas_poyas_kak'] != 'по региону'], 'пояс у всех «по региону»: %s' %
             collections.Counter(r['chas_poyas_kak'] for r in rows))
    print('      сегменты в базе: %s' % (schyot_segmentov(rows),))
    print('      пометки: %s' % collections.Counter((r.get('pometka_ocheredi') or '').split(':')[0] for r in rows))
    print('      клиент СЦ: %d, со сделками: %d' % (sum(1 for r in rows if r.get('bitrix_klient_sc')),
                                                  sum(1 for r in rows if r.get('bitrix_sdelok'))))
    vnutr = next(z for z in vars(create_app()).values() if hasattr(z, 'routes') and hasattr(z, 'dependency_overrides'))
    ADMIN = {'id': 0, 'username': 'meyer_admin', 'role': 'admin', 'is_active': 1}
    PROD = {'id': 1, 'username': 'meyer2', 'role': 'sales', 'is_active': 1}

    def chislo(t):
        m = re.search(r'<b class="total-count">(\d+) компаний</b>', t)
        return int(m.group(1)) if m else -1

    vnutr.dependency_overrides[rcs.current_user] = lambda: ADMIN
    with TestClient(vnutr) as kl:
        o = kl.get(PUT + '/centro')
        t = o.text
        proverit(o.status_code == 200, 'главная (директор): %s, %d компаний' % (o.status_code, chislo(t)))
        bloki = re.findall(r'<select name="region"[^>]*>(.*?)</select>', t, re.S)
        opcii = sorted({v for b in bloki for v in re.findall(r'<option value="([^"]+)"', b)})
        myagko(bool(opcii), 'выпадающий «Регион» найден на главной')
        proverit(not [v for v in opcii if v not in OFICIALNYE],
                 'выпадающий «Регион»: %d значений, вне официальных: %s' % (len(opcii), [v for v in opcii if v not in OFICIALNYE]))
        proverit(not {'Иванково', 'Орловка'} & set(opcii), 'в «Регионе» нет «Иванково»/«Орловка»')
        bs = re.findall(r'<select name="segment"[^>]*>(.*?)</select>', t, re.S)
        sopc = re.findall(r'<option value="([^"]+)"[^>]*>[^<]*?– (\d+)</option>', bs[0]) if bs else []
        print('      выпадающий «Сегмент» (директор): %s, сумма %d' % (sopc, sum(int(x[1]) for x in sopc)))
        m = re.search(r'Сейчас рабочее время у компании · (\d+)', t)
        try:
            skrytye = set(rcs.sales.hidden_companies() or ())
        except Exception:  # noqa: BLE001
            skrytye = set()
        ozhid = sum(1 for r in rows if r['inn'] not in skrytye and rcs._rabochee_vremya(r))
        (proverit if m else myagko)(m and int(m.group(1)) == ozhid, '«Сейчас рабочее время»: в фильтре %s, по поясам базы %d (UTC %s)' % (
            m.group(1) if m else '?', ozhid, time.strftime('%H:%M', time.gmtime())))
        o = kl.get(PUT + '/centro', params={'rabochee': '1'})
        proverit(o.status_code == 200, 'список «Сейчас рабочее время»: %s, %d компаний' % (o.status_code, chislo(o.text)))
        for inn in ('6381022763', '6453143086', '682708704703', '3705008974'):
            r = po_inn.get(inn)
            if r:
                print('      %s %s: регион «%s», UTC+%s, сейчас рабочее: %s' % (
                    inn, r['predpriyatie'][:30], r['region'], r['chas_poyas'], rcs._rabochee_vremya(r)))
        o = kl.get(PUT + '/centro', params={'q': 'ОРЛОВСКИЙ', 'region': 'Самарская область'})
        proverit(o.status_code == 200 and chislo(o.text) >= 1, 'фильтр «Самарская область» находит Маслосырзавод Орловский: %d' % chislo(o.text))
        o = kl.get(PUT + '/centro', params={'segment': '3 пищевые'})
        proverit(o.status_code == 200, 'фильтр «3 пищевые»: %s, %d' % (o.status_code, chislo(o.text)))
        for inn, nado, nelzya in (('6381022763', ['Самарская область'], ['Орловка</']),
                                  ('682708704703', ['Тамбовская область'], []),
                                  ('7743176818', ['<b>Сегмент</b> 3 пищевые</span>'], ['семеноводы, 3 пищевые']),
                                  ('3443002556', ['<b>Сегмент</b> 3 пищевые</span>'], []),
                                  ('7826087713', [], []), ('2245002584', [], []), ('2344007569', [], [])):
            o = kl.get(PUT + '/centro', params={'inn': inn})
            if o.status_code == 404 and inn in skrytye:
                myagko(False, 'карточка %s скрыта продавцом (404) – не проверяю' % inn)
                continue
            proverit(o.status_code == 200 and not any(x in o.text for x in nelzya), 'карточка %s: %s' % (inn, o.status_code))
            myagko(all(x in o.text for x in nado), 'карточка %s: %s %s' % (inn, o.status_code, re.sub(r'<[^>]+>', ' ', ''.join(
                re.findall(r'<span><b>(?:Регион|Сегмент|Попадание)</b>[^<]*</span>', o.text)))))
        o = kl.get(PUT + '/centro/stats')
        proverit(o.status_code == 200, 'статистика директора: %s' % o.status_code)
    vnutr.dependency_overrides[rcs.current_user] = lambda: PROD
    with TestClient(vnutr) as kl:
        o = kl.get(PUT + '/centro')
        proverit(o.status_code == 200, 'главная продавца meyer2: %s, %d компаний' % (o.status_code, chislo(o.text)))
        o = kl.get(PUT + '/centro', params={'rabochee': '1'})
        proverit(o.status_code == 200, 'продавец, «Сейчас рабочее время»: %s, %d' % (o.status_code, chislo(o.text)))
    try:
        os.remove(TEST_DB)
    except OSError as e:
        print('временная копия не удалена: %s' % e)
    print('ПЛОХИХ ПРОВЕРОК: %d' % plohih)
    raise SystemExit(1 if plohih else 0)


def otkat(zhurnal):
    """Откат по своему журналу: ячейка возвращается в «было», только если сейчас в ней «стало»."""
    zap = json.load(io.open(zhurnal, encoding='utf-8'))['zapisi']
    k = sqlite3.connect(KAT, timeout=60)
    n = propusk = 0
    with k:
        for z in zap:
            tek = k.execute('select "%s" from company where inn=?' % z['kolonka'], (z['inn'],)).fetchone()
            if tek is None or tek[0] != z['stalo']:
                propusk += 1
                continue
            k.execute('UPDATE company SET "%s"=? WHERE inn=?' % z['kolonka'], (z['bylo'], z['inn']))
            n += 1
    k.close()
    print('откат: возвращено ячеек %d, пропущено (уже изменены другими) %d' % (n, propusk))


if '--otkat' in sys.argv:
    otkat(os.path.join(DROP, os.path.basename(sys.argv[sys.argv.index('--otkat') + 1])))
    raise SystemExit(0)

# ====================================================================== ОСНОВНОЙ ХОД
if __name__ == '__main__':
    SUHOY = '--suhoy' in sys.argv
    METKA = time.strftime('%Y%m%d-%H%M%S')
    k = sqlite3.connect(KAT, timeout=60)
    k.row_factory = sqlite3.Row
    rows = [dict(r) for r in k.execute('select * from company')]
    for imya, _ in NOVYE_KOLONKI:
        for r in rows:
            r.setdefault(imya, None)
    do = schyot_segmentov(rows)
    izm, sch = plan(rows)
    po_inn = {r['inn']: r for r in rows}
    zapisi = []
    for inn, n, poch in izm:
        for kk, v in n.items():
            zapisi.append({'inn': inn, 'predpriyatie': po_inn[inn].get('predpriyatie'), 'kolonka': kk,
                           'bylo': po_inn[inn].get(kk), 'stalo': v, 'pochemu': poch.get(kk, '')})
    posle_rows = [dict(r, **dict(next((n for i, n, _ in izm if i == r['inn']), {}))) for r in rows]
    posle = schyot_segmentov(posle_rows)
    print('компаний с изменениями: %d, ячеек: %d' % (len(izm), len(zapisi)))
    print(json.dumps(sch, ensure_ascii=False, indent=0))
    print('сегменты ДО:    %s; сумма %d, компаний с сегментом %d' % do)
    print('сегменты ПОСЛЕ: %s; сумма %d, компаний с сегментом %d' % posle)
    dva = [(r['inn'], r['okved'], r['segment']) for r in posle_rows if len(segs(r.get('segment'))) > 1]
    print('компаний с двумя сегментами по основному коду: %d %s' % (len(dva), sorted({(x[1], x[2]) for x in dva})))
    for r in posle_rows:
        if r.get('pometka_ocheredi'):
            print('   ПОМЕТКА %s %s: %s' % (r['inn'], (r.get('predpriyatie') or '')[:40], r['pometka_ocheredi']))
    for z in zapisi:
        if z['kolonka'] in ('region', 'chas_poyas', 'popadanie'):
            print('   %s %s %s: %r -> %r' % (z['inn'], (z['predpriyatie'] or '')[:30], z['kolonka'], z['bylo'], z['stalo']))
    plan_put = os.path.join(DROP, 'fixE1_%s_%s.json' % ('plan' if SUHOY else 'zhurnal', METKA))
    io.open(plan_put, 'w', encoding='utf-8').write(json.dumps(
        {'metka': METKA, 'suhoy': SUHOY, 'schyotchiki': sch, 'segmenty_do': do, 'segmenty_posle': posle,
         'zapisi': zapisi}, ensure_ascii=False, indent=1))
    print('журнал/план: %s' % plan_put)
    if SUHOY:
        raise SystemExit(0)

    B = os.path.join(KOREN, '_bekap', 'fixE1-' + METKA)
    os.makedirs(B, exist_ok=True)
    kop = sqlite3.connect(os.path.join(B, 'meyer_baza1.db'))
    povtor(k.backup, kop)
    kop.close()
    print('копия каталога: %s' % B)

    def zapisat():
        kol = {r[1] for r in k.execute('PRAGMA table_info(company)')}
        with k:
            for imya, tip in NOVYE_KOLONKI:
                if imya not in kol:
                    k.execute('ALTER TABLE company ADD COLUMN %s %s' % (imya, tip))
            for inn, n, _ in izm:
                k.execute('UPDATE company SET %s WHERE inn=?' % ', '.join('"%s"=?' % kk for kk in n),
                          list(n.values()) + [inn])
            # проверка до commit: всё записалось и регионы официальные
            neof = k.execute('select count(*) from company where coalesce(region,"") not in (%s)' %
                             ','.join('?' * len(OFICIALNYE)), sorted(OFICIALNYE)).fetchone()[0]
            if neof:
                raise RuntimeError('после записи регионов вне официального списка: %d' % neof)
    try:
        povtor(zapisat)
    except Exception as e:  # noqa: BLE001
        print('ЗАПИСЬ НЕ УДАЛАСЬ, транзакция откатилась: %r' % e)
        raise SystemExit(1)
    k.close()
    print('записано: %d компаний, %d ячеек' % (len(izm), len(zapisi)))
    r = subprocess.run([VENV, os.path.abspath(__file__), '--proverka'], capture_output=True, timeout=1200, cwd=KOREN,
                       env=dict(os.environ, PYTHONIOENCODING='utf-8'))
    sys.stdout.write(r.stdout.decode('utf-8', 'replace')[-4500:])
    if r.returncode:
        sys.stdout.write(r.stderr.decode('utf-8', 'replace')[-2000:])
        print('ПРОВЕРКА НЕ ПРОШЛА – откат по своему журналу')
        otkat(plan_put)
        raise SystemExit(1)
    print('ГОТОВО')
