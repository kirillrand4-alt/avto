# -*- coding: utf-8 -*-
"""
Анализ чистоты выгрузки ЭПБ по центробежному оборудованию.

Вход:  seo-texts/engineers-lens/centro/epb-centro-vse.csv  (7 750 заключений, 347 предприятий)
Выход: seo-texts/engineers-lens/centro/epb-centro-ochishchennyy.csv  (та же выгрузка + 3 колонки)
       + печать всех метрик в stdout (из них собран ANALIZ-chistota.md)

Закрываем шесть записанных долгов:
  1) доля насосов среди «нагнетателей»;
  2) двойной счёт одной машины в заключениях разных лет;
  3) реорганизации (один завод под двумя ИНН);
  4) предприятия только с ЗС (обвязка есть, машины в реестре нет);
  5) география и отрасль;
  6) топ экспертных организаций.

Сеть не используется, только локальный CSV.
"""

import csv
import re
import sys
import collections
import difflib
import os

BASE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(BASE, 'engineers-lens', 'centro', 'epb-centro-vse.csv')
DST = os.path.join(BASE, 'engineers-lens', 'centro', 'epb-centro-ochishchennyy.csv')


# ────────────────────────────────────────────────────────────────────────────
# 0. Чтение
# ────────────────────────────────────────────────────────────────────────────

def load(path=SRC):
    # в файле BOM и разделитель ';'
    with open(path, encoding='utf-8-sig', newline='') as f:
        return list(csv.DictReader(f, delimiter=';'))


# ────────────────────────────────────────────────────────────────────────────
# 1. Классификация объекта: компрессор / насос / обвязка / неопределимо
# ────────────────────────────────────────────────────────────────────────────
# Поле obekt — свободный текст. В нём обычно смешаны три слоя:
#   а) шапка заключения («ЗАКЛЮЧЕНИЕ ЭКСПЕРТИЗЫ… на техническое устройство»),
#   б) описание ОПО («применяемое на опасном производственном объекте
#      "Площадка компрессорной станции…", рег. № А58-…, I класс опасности»),
#   в) собственно объект («Корпус центробежного нагнетателя Н-370-18-1 зав. № 6457»).
# Слои (а) и (б) содержат слова-ловушки («площадка», «компрессорная станция»),
# поэтому их вычищаем, а класс определяем по ПЕРВОМУ по позиции ключевому слову
# в остатке: что стоит раньше — то и есть главное существительное объекта.

NOISE = [re.compile(p, re.I) for p in [
    # скобка со свидетельством о регистрации ОПО целиком
    r'\([^)]{0,400}свидетельств\w+\s+о\s+регистрации[^)]{0,400}\)',
    r'заключени\w*\s+экспертиз\w*\s+промышленн\w*\s+безопасност\w*',
    r'экспертиз\w*\s+промышленн\w*\s+безопасност\w*',
    r'наименование\s+заключени\w*',
    r'объект\w*\s+экспертиз\w*',
    r'эксплуатирующ\w+\s+организаци\w*\s*[:\-–—]?\s*[^\.]{0,150}\.',
    # название ОПО в кавычках после слова «объект»
    r'(?:наименовани\w*\s+)?объект\w*\s*[-–—:]?\s*[«"][^»"]{0,200}[»"]',
    r'примен\w+\s+(?:на|при|в)\s+(?:эксплуатации\s+)?'
    r'(?:опасн\w+\s+производственн\w+\s+объект\w*|опо)',
    r'опасн\w+\s+производственн\w+\s+объект\w*\s*(?:\(опо\))?',
    r'в\s+случаях,?\s+установленн\w+\s+статьей\s+7[^\.]{0,250}',
    r'рег(?:истрационн\w*)?\.?\s*№\s*[^\s,;]+',
    r'класс\w*\s+опасност\w*\s*(?:опо)?\s*[-–—:]?\s*[IVX0-9]+',
    r'принадлежащ\w+\s+[^,\.;]{0,80}',
    r'техническ\w+\s+устройств\w*',
]]


def clean(t):
    """Снять шапку заключения и описание ОПО, оставить описание объекта."""
    t = t.replace('\xa0', ' ')
    for p in NOISE:
        t = p.sub(' ', t)
    return re.sub(r'\s+', ' ', t).strip(' «»"\'()[]№:-–—,.;')


# машина, которую мы продаём (или её корпус/ротор — это тоже она)
MACH = (r'(?:компрессор(?!н\w*\s+(?:цех|станци|зал|отдел|участок|дом|котельн))'
        r'|нагнетател|воздуходувк|турбокомпрессор|турбовоздуходувк|турбогазодувк'
        r'|газодувк|\bцбн\b|турбоагрегат|турбомашин|газоперекачивающ|\bгпа\b)')
# насос
PUMP = r'(?:насос|помп\w)'
# обвязка и вспомогательное оборудование уровня устройства
AUX_DEV = (
    r'(?:трубопровод|паропровод|газопровод|маслопровод|продуктопровод|воздуховод|газоход|коллектор|'
    r'арматур|задвижк|\bкран\w*\b|клапан|вентил[ья]|сосуд|[ёе]мкост|маслобак|ресивер|баллон|'
    r'воздухоохладител|маслоохладител|теплообменник|холодильник|фильтр|сепаратор|влагоотделител|'
    r'адсорбер|осушител|электродвигател|электропривод|двигател|турбин|редуктор|мультипликатор|муфт|'
    r'генератор|вентилятор|дымосос|маслосистем|маслостанц|перепускн|воздухозаборн|конденсатор|'
    r'деаэратор|котел|кот[её]л|печ[ьи]|цистерн|лифт|подъ[её]мник|дефлегматор|скруббер|циклон|'
    r'аппарат\w*\s+воздушн)')
# здания и сооружения — учитываем только для строк с tip=ЗС: у ТУ (технического
# устройства) «площадка»/«здание» — всегда адрес ОПО, а не сам объект
AUX_STRUCT = (r'(?:здани|сооружени|фундамент|эстакад|галере|помещени|\bзал\w*\b|отсек|площадк|'
              r'укрыти|кожух|дымов\w+\s+труб|градирн|резервуар|силос|бункер|навес|'
              r'наружн\w+\s+установк)')

MACH_RE = re.compile(MACH, re.I)
PUMP_RE = re.compile(PUMP, re.I)
AUXD_RE = re.compile(AUX_DEV, re.I)
AUXS_RE = re.compile(AUX_STRUCT, re.I)


def klass_of(txt, tip):
    """Вернуть (класс, очищенный текст). Побеждает слово с наименьшей позицией."""
    def run(t):
        pos = {}
        for name, rx in (('компрессор', MACH_RE), ('насос', PUMP_RE), ('обвязка', AUXD_RE)):
            m = rx.search(t)
            if m:
                pos[name] = m.start()
        if tip == 'ЗС':
            m = AUXS_RE.search(t)
            if m:
                pos['обвязка'] = min(pos.get('обвязка', 10 ** 9), m.start())
        return min(pos, key=pos.get) if pos else None

    t = clean(txt)
    # если чистка съела всё полезное — пробуем по сырому тексту
    return (run(t) or run(txt) or 'неопределимо'), t


# ────────────────────────────────────────────────────────────────────────────
# 2. Заводские / инвентарные номера и марка машины
# ────────────────────────────────────────────────────────────────────────────
# «зав. № 6457», «зав.№88007», «заводской номер 19», «зав №9186».
# Требуем знак № или слово «номер» — иначе ловится «…гелиевого завода…».
ZAV = re.compile(
    r'зав(?:\.|одско\w*)?\s*(?:№|номер\w*)\s*№*\s*'
    r'([^\s,;\)\]\(]+(?:\s+[0-9][0-9A-Za-zА-Яа-я\-/\.]*)*)', re.I)
INV = re.compile(r'инв(?:\.|ентарн\w*)?\s*(?:№|номер\w*)\s*№*\s*([^\s,;\)\]\(]+)', re.I)

# кириллица, визуально совпадающая с латиницей (в номерах пишут вперемешку)
TRANSLIT = str.maketrans('АВЕКМНОРСТУХ', 'ABEKMHOPCTYX')
EMPTY_NUM = re.compile(r'Б\s*[/\\.]?\s*Н\.?|Н\s*/\s*У|НЕТ|ОТСУТСТВУЕТ|НЕ\s*УКАЗАН\w*|-+', re.I)
# «зав.№ ЦНД - 463-10-4033-F» — ЦНД/ЦВД/ЦСД это не номер, а ступень
STAGE = {'ЦНД', 'ЦВД', 'ЦСД', 'НД', 'ВД', 'СД'}


def norm_num(v):
    """Нормализовать номер; вернуть '' если номера фактически нет."""
    v = v.strip().strip('«».,;:"\'()[]-').upper().replace('Ё', 'Е')
    if not v or EMPTY_NUM.fullmatch(v):
        return ''
    if v in STAGE:
        return ''
    v = re.sub(r'\s+', '', v.translate(TRANSLIT))
    # без цифры это почти всегда мусор от распознавания («МАСГЖ», «ЕОЖVP»)
    return v if re.search(r'\d', v) else ''


def first_num(rx, t):
    for m in rx.finditer(t):
        v = norm_num(m.group(1))
        if v:
            return v
    return ''


# марка машины: «К354-101-1», «Н-370-18-1», «2ГЦ2-40/51-60», «ТВ-80-1,6».
# Нужна, чтобы не склеить в одну машину разные агрегаты с «зав. № 1».
LABEL_BEFORE = re.compile(r'(?:зав|инв|поз|техн?|тех|ст|станц|рег|№|инд)\W{0,4}$', re.I)
TOKEN = re.compile(r'[A-ZА-ЯЁa-zа-яё0-9]{2,}(?:[-/][A-ZА-ЯЁa-zа-яё0-9]+)+'
                   r'|[A-ZА-ЯЁ]{1,4}\s?\d{2,4}[-/][\d\-/,А-ЯA-Z]+')


def mark_of(t):
    """Первый токен, похожий на марку и не идущий сразу за «зав./инв./поз.»."""
    for m in TOKEN.finditer(t):
        s = m.group(0)
        if not re.search(r'\d', s) or not re.search(r'[A-ZА-ЯЁa-zа-яё]', s):
            continue
        if LABEL_BEFORE.search(t[max(0, m.start() - 14):m.start()]):
            continue
        v = re.sub(r'[^0-9A-ZА-Я]', '', s.upper().replace('Ё', 'Е')).translate(TRANSLIT)
        if len(v) >= 4:
            return v
    return ''


def machine_key(row, zav, inv, mark):
    """
    Ключ машины. Заводской номер приоритетнее инвентарного.
    Короткий номер (1–2 знака) сам по себе не уникален внутри завода
    («зав. № 1» у Башнефти — семь разных агрегатов), поэтому к нему
    добавляем марку.
    """
    inn = row['inn_zakazchika']
    if zav:
        return (inn, 'Z', zav, mark if len(zav) <= 2 else '')
    if inv:
        return (inn, 'I', inv, mark if len(inv) <= 2 else '')
    return None


# ────────────────────────────────────────────────────────────────────────────
# 3. Нормализация названия юрлица (для поиска реорганизаций)
# ────────────────────────────────────────────────────────────────────────────
FORMS = (r'^(?:ОАО|ООО|ПАО|АО|ЗАО|НАО|АООТ|ФГУП|ГУП|МУП|ГБУ|ФКП|ФГБУ|ФГУ|'
         r'ПО|НПО|НПП|УК|ТД|СП|ГК|АК|НК|ОП)\b')


def norm_name(n):
    n = n.upper().replace('Ё', 'Е')
    n = re.sub(r'\(ИНН\s*\d+\)', '', n)
    n = re.sub(r'["«»\'`]', ' ', n)
    n = re.sub(r'\s+', ' ', n).strip()
    prev = None
    while prev != n:                       # ООО «ТД КМЗ» → КМЗ
        prev = n
        n = re.sub(FORMS, '', n).strip(' -,.')
        n = re.sub(r'^(?:ИМ\.|ИМЕНИ)\b', '', n).strip()
    return re.sub(r'[^А-ЯA-Z0-9]', '', n)


# ────────────────────────────────────────────────────────────────────────────
# 4. Регион по первым двум цифрам ИНН
# ────────────────────────────────────────────────────────────────────────────
# Это регион НАЛОГОВОЙ РЕГИСТРАЦИИ юрлица, а не адрес площадки.
REGIONS = {
    '01': 'Адыгея', '02': 'Башкортостан', '03': 'Бурятия', '04': 'Алтай (респ.)',
    '05': 'Дагестан', '06': 'Ингушетия', '07': 'Кабардино-Балкария', '08': 'Калмыкия',
    '09': 'Карачаево-Черкесия', '10': 'Карелия', '11': 'Коми', '12': 'Марий Эл',
    '13': 'Мордовия', '14': 'Якутия', '15': 'Северная Осетия', '16': 'Татарстан',
    '17': 'Тыва', '18': 'Удмуртия', '19': 'Хакасия', '20': 'Чечня', '21': 'Чувашия',
    '22': 'Алтайский край', '23': 'Краснодарский край', '24': 'Красноярский край',
    '25': 'Приморский край', '26': 'Ставропольский край', '27': 'Хабаровский край',
    '28': 'Амурская обл.', '29': 'Архангельская обл.', '30': 'Астраханская обл.',
    '31': 'Белгородская обл.', '32': 'Брянская обл.', '33': 'Владимирская обл.',
    '34': 'Волгоградская обл.', '35': 'Вологодская обл.', '36': 'Воронежская обл.',
    '37': 'Ивановская обл.', '38': 'Иркутская обл.', '39': 'Калининградская обл.',
    '40': 'Калужская обл.', '41': 'Камчатский край', '42': 'Кемеровская обл.',
    '43': 'Кировская обл.', '44': 'Костромская обл.', '45': 'Курганская обл.',
    '46': 'Курская обл.', '47': 'Ленинградская обл.', '48': 'Липецкая обл.',
    '49': 'Магаданская обл.', '50': 'Московская обл.', '51': 'Мурманская обл.',
    '52': 'Нижегородская обл.', '53': 'Новгородская обл.', '54': 'Новосибирская обл.',
    '55': 'Омская обл.', '56': 'Оренбургская обл.', '57': 'Орловская обл.',
    '58': 'Пензенская обл.', '59': 'Пермский край', '60': 'Псковская обл.',
    '61': 'Ростовская обл.', '62': 'Рязанская обл.', '63': 'Самарская обл.',
    '64': 'Саратовская обл.', '65': 'Сахалинская обл.', '66': 'Свердловская обл.',
    '67': 'Смоленская обл.', '68': 'Тамбовская обл.', '69': 'Тверская обл.',
    '70': 'Томская обл.', '71': 'Тульская обл.', '72': 'Тюменская обл.',
    '73': 'Ульяновская обл.', '74': 'Челябинская обл.', '75': 'Забайкальский край',
    '76': 'Ярославская обл.', '77': 'Москва', '78': 'Санкт-Петербург',
    '79': 'Еврейская АО', '81': 'Коми-Пермяцкий АО (Пермский край)',
    '83': 'Ненецкий АО', '84': 'Таймырский АО (Красноярский край)',
    '86': 'ХМАО — Югра', '87': 'Чукотский АО', '88': 'Эвенкийский АО (Красноярский край)',
    '89': 'ЯНАО', '91': 'Крым', '92': 'Севастополь', '93': 'ДНР', '94': 'ЛНР',
    '99': 'иностранная организация (филиал в РФ)',
}

# грубая отраслевая раскладка по названию юрлица + тексту объектов
INDUSTRY = [
    ('газотранспорт и газодобыча',
     r'ТРАНСГАЗ|ГАЗПРОМ ДОБЫЧА|ГАЗПРОМ ПЕРЕРАБОТКА|ГАЗПРОМ ГЕЛИЙ|СИБУРТЮМЕНЬГАЗ|ГАЗПРОМ ИНВЕСТ|'
     r'НОВАТЭК|ГАЗПРОМ СПГ|ЧЕРНОМОРНЕФТЕГАЗ|ГАЗПРОМ ДОБ'),
    ('нефтедобыча и нефтепереработка',
     r'НЕФТЕГАЗ|НПЗ|НЕФТЬ|ЛУКОЙЛ|ТАТНЕФТЬ|СЛАВНЕФТЬ|ГАЗПРОМНЕФТЬ|РОСНЕФТЬ|АНХК|ННК|'
     r'НЕФТЕОРГСИНТЕЗ|НЕФТЕХИМСЕРВИС|СУРГУТНЕФТЕГАЗ|УДМУРТНЕФТЬ|ТАНЕКО|НЕФТЕПЕРЕРАБ'),
    ('химия, нефтехимия, удобрения',
     r'ХИМ|АЗОТ|АММИАК|АКРОН|УРАЛХИМ|УРАЛКАЛИЙ|ФОСАГРО|АПАТИТ|МИНУДОБРЕНИЯ|КАУСТИК|СИБУР|'
     r'ОРГСИНТЕЗ|ПОЛИМЕР|ТОАЗ|КУЙБЫШЕВАЗОТ|ЩЕКИНОАЗОТ|МЕТАФРАКС|ГАЛОПОЛИМЕР|СОДА|ПЛАСТ|'
     r'ЭТИЛЕН|СТАВРОЛЕН|ЗАПСИБНЕФТЕХИМ|КРИОГЕН|ТЕХНИЧЕСКИЕ ГАЗЫ|ЛИНДЕ|ЭЙР ЛИКИД|ПРАКСАЙР'),
    ('чёрная металлургия и кокс',
     r'МЕТКОМБИНАТ|МЕТАЛЛУРГ|ЕВРАЗ|ММК|НЛМК|СЕВЕРСТАЛЬ|МЕЧЕЛ|КОКС|ТРУБН|ТМК|ЧТПЗ|ПНТЗ|СТЗ|'
     r'ЗСМК|НТМК|ОЭМК|УРАЛВАГОНЗАВОД|ЧМК|АЛЧЕВСК|ДМЗ|ФЕРРОСПЛАВ'),
    ('цветная металлургия',
     r'РУСАЛ|НОРИЛЬСК|КОЛЬСКАЯ ГМК|УГМК|ЭЛЕКТРОЦИНК|ЧЦЗ|ЦИНК|МЕДЬ|МЕДНОГОРСК|СВЯТОГОР|'
     r'КАРАБАШМЕДЬ|ГЛИНОЗЕМ|АЛЮМИНИ|ТИТАН|ПОЛЮС|ЮГМК'),
    ('горная добыча и обогащение',
     r'ГОК|РУДНИК|РАЗРЕЗ|ШАХТА|ОБОГАТИТЕЛ|ЦОФ|\bОФ\b|ГОФ|КАРЬЕР|ОКАТЫШ|ППГХО|УГОЛ|КУЗБАСС|'
     r'РАСПАДСК|СУЭК|ЯКУТУГОЛЬ|ЮЖНЫЙ КУЗБАСС'),
    ('энергетика (ТЭЦ, ГРЭС)',
     r'ЭНЕРГО|ТГК|ОГК|ГРЭС|ТЭЦ|ЮНИПРО|Т ПЛЮС|ДГК|БГК|ИНТЕР РАО|КВАДРА|ФОРВАРД'),
    ('ЖКХ, водоснабжение, очистные',
     r'ВОДОКАНАЛ|ВОДОСНАБ|ОЧИСТН|АКВА|ВОДА|ПРОМВОДОКАНАЛ|ТЕПЛОСЕТ|КОММУНАЛ'),
    ('целлюлоза, бумага, дерево',
     r'ЦБК|ЦБП|БУМАЖ|ЦЕЛЛЮЛОЗ|ИЛИМ|СВЕЗА|КРОНО|ЛЕС|КАРТОН|КБК'),
    ('пищевая промышленность',
     r'МЕЛЬКОМБИНАТ|ХЛЕБ|САХАР|МОЛОК|МЯСО|ПИВО|ДРОЖЖ|КРАХМАЛ|СПИРТ|МАСЛОЖИР|ЭФКО|ЭЛЕКОМ'),
]


def industry_of(name, texts):
    blob = (name + ' ' + ' '.join(texts)).upper().replace('Ё', 'Е')
    for label, pat in INDUSTRY:
        if re.search(pat, blob):
            return label
    return 'прочее / не определено'


# ────────────────────────────────────────────────────────────────────────────
# Основной проход
# ────────────────────────────────────────────────────────────────────────────

def main():
    out = sys.stdout
    P = lambda *a: print(*a, file=out)

    rows = load()
    P('Строк: %d, уникальных номеров заключений: %d, предприятий: %d, ЭО: %d'
      % (len(rows), len(set(r['nomer'] for r in rows)),
         len(set(r['inn_zakazchika'] for r in rows)), len(set(r['inn_eo'] for r in rows))))
    P('tip: %s' % dict(collections.Counter(r['tip'] for r in rows)))
    P('srok: %s' % dict(collections.Counter(r['srok'] for r in rows)))
    P('zapros: %s' % dict(collections.Counter(r['zapros'] for r in rows)))

    # ── обогащение строк
    enriched = []
    for r in rows:
        o = r['obekt']
        k, cleaned = klass_of(o, r['tip'])
        zav = first_num(ZAV, o)
        inv = first_num(INV, o)
        mark = mark_of(o)
        enriched.append(dict(row=r, klass=k, clean=cleaned, zav=zav, inv=inv, mark=mark))

    # ── ключ машины и дубли
    for e in enriched:
        e['key'] = machine_key(e['row'], e['zav'], e['inv'], e['mark'])
    keycnt = collections.Counter(e['key'] for e in enriched if e['key'])
    for e in enriched:
        e['dubl'] = 'н/д' if not e['key'] else ('да' if keycnt[e['key']] > 1 else 'нет')

    ent_name = {}
    for r in rows:
        ent_name.setdefault(r['inn_zakazchika'], r['zakazchik'])

    # ══ 1. Нагнетатели: компрессор или насос ═══════════════════════════════
    P('\n' + '=' * 70 + '\n1. НАГНЕТАТЕЛИ: КОМПРЕССОР ИЛИ НАСОС\n' + '=' * 70)
    nag = [e for e in enriched if 'нагнетат' in e['row']['obekt'].lower()]
    P('строк со словом «нагнетат»: %d (%.1f%% выгрузки), предприятий: %d'
      % (len(nag), 100 * len(nag) / len(rows),
         len(set(e['row']['inn_zakazchika'] for e in nag))))

    # 1.1 Что стоит СРАЗУ после слова «нагнетатель» — прямое указание среды
    after = collections.Counter()
    for e in nag:
        for m in re.finditer(r'нагнетател\w*\s+([А-Яа-яЁё]{3,})', e['row']['obekt'], re.I):
            after[m.group(1).lower()] += 1
    P('\nслово сразу после «нагнетатель» (топ-25): %s' % after.most_common(25))

    # 1.2 Контроль регулярок: сначала проверяем, что шаблон вообще срабатывает
    liquid_pat = r'нагнетател\w*\s+(?:вод[ыуе]|жидкост|раствор|пульп|нефт|мазут|кислот|шлам|масл)'
    gas_pat = r'нагнетател\w*\s+(?:природн|коксов|полукоксов|нитрозн|доменн|газ|воздух|кислород|азот|аммиак)'
    n_liq = sum(1 for r in rows if re.search(liquid_pat, r['obekt'], re.I))
    n_gas = sum(1 for r in rows if re.search(gas_pat, r['obekt'], re.I))
    P('\nконтроль шаблонов (тот же движок, разные среды):')
    P('  «нагнетатель <газ/воздух…>»  : %d строк   ← шаблон рабочий' % n_gas)
    P('  «нагнетатель <вода/жидкость…>»: %d строк' % n_liq)
    for p in (r'нагнетательн\w*\s+насос', r'насос[\s-]*нагнетател', r'нагнетател\w*\s+насос'):
        P('  «%s»: %d' % (p, sum(1 for r in rows if re.search(p, r['obekt'], re.I))))

    # 1.3 Три группы
    GAS_EV = (r'компрессор|воздуходувк|турбокомпрессор|турбовоздуходувк|газодувк|\bгпа\b|\bцбн\b|\bспч\b|'
              r'лпумг|компрессорн\w+\s+(?:станци|цех)|\bкс[\s-]?\d|газоперекачивающ|'
              r'природн\w+\s+газ|коксов\w+\s+газ|полукоксов|нитрозн|доменн|технологическ\w+\s+газ|'
              r'\bгаза\b|\bгазу\b|\bгаз\b|воздух|кислород|\bазот|аммиак|этилен|пропилен|водород|'
              r'дуть[её]|абгаз|углекислот|хлор|фреон|сероводород|попутн\w+\s+нефтян')
    # типовые марки ЦБН/турбокомпрессоров: Н-370-18-1, НЦ-16/76, Э-1700-11-2М, 650-21-2, RF-2BB…
    MARK_EV = (r'\bн[\s-]?\d{2,4}[-/]\d{1,3}[-/]\d|\bнц[вэ]{0,2}[\s-]?\d|\bэ[\s-]?\d{3,4}-\d|'
               r'\b\d{3,4}-\d{2}-\d\b|\brf[\s-]?\d|\b\d?bcl\b|\bpcl\b|\bгтк[\s-]?\d|\bгпу[\s-]?\d|'
               r'\bтв[\s-]?\d{2}|\bцк[\s-]?\d|\bк[\s-]?\d{3}-\d')
    gas_re, mark_re = re.compile(GAS_EV, re.I), re.compile(MARK_EV, re.I)
    liq_re = re.compile(liquid_pat, re.I)

    grp = collections.Counter()
    examples = collections.defaultdict(list)
    for e in nag:
        o = e['row']['obekt']
        if e['klass'] == 'насос' or liq_re.search(o):
            g = 'насос / жидкость'
        elif gas_re.search(o) or mark_re.search(o):
            g = 'компрессорное оборудование'
        else:
            g = 'неопределимо'
        e['nag_group'] = g
        grp[g] += 1
        if len(examples[g]) < 8:
            examples[g].append(o[:150])
    P('\nтри группы среди «нагнетателей»:')
    for g, c in grp.most_common():
        P('  %-28s %5d  %5.1f%%' % (g, c, 100 * c / len(nag)))
    for g in examples:
        P('\n  примеры «%s»:' % g)
        for x in examples[g]:
            P('    · %s' % x)
    P('\n  внутри «компрессорного» по klass: %s'
      % dict(collections.Counter(e['klass'] for e in nag if e['nag_group'] == 'компрессорное оборудование')))
    P('  внутри «неопределимо» по klass: %s'
      % dict(collections.Counter(e['klass'] for e in nag if e['nag_group'] == 'неопределимо')))

    # 1.4 Бонус: ЦНД — цилиндр низкого давления паровой турбины, не компрессор
    P('\nБонусная проверка: ЦНД')
    cnd = [e for e in enriched if re.search(r'\bЦНД\b', e['row']['obekt'])]
    cnd_turb = [e for e in cnd
                if not re.search(r'компрессор|нагнетател|воздуходувк', e['row']['obekt'], re.I)
                or re.search(r'паров\w+\s+турбин|турбоагрегат|ТЭЦ|ГРЭС|энергоблок|перепускн|паропуск|'
                             r'\bТГ-\d|\bТА-\d|цилиндр\w*\s+низкого', e['row']['obekt'], re.I)]
    P('  строк с ЦНД: %d, из них похожих на паровую турбину: %d' % (len(cnd), len(cnd_turb)))
    P('  предприятия с ЦНД (топ): %s'
      % collections.Counter(e['row']['zakazchik'] for e in cnd).most_common(8))
    for e in cnd_turb[:4]:
        P('    · %s' % e['row']['obekt'][:130])

    # ══ 2. Двойной счёт машины ═════════════════════════════════════════════
    P('\n' + '=' * 70 + '\n2. ДВОЙНОЙ СЧЁТ ОДНОЙ МАШИНЫ\n' + '=' * 70)
    n_zav = sum(1 for e in enriched if e['zav'])
    n_inv = sum(1 for e in enriched if e['inv'])
    n_any = sum(1 for e in enriched if e['key'])
    P('строк с заводским номером: %d (%.1f%%)' % (n_zav, 100 * n_zav / len(rows)))
    P('строк с инвентарным номером: %d (%.1f%%)' % (n_inv, 100 * n_inv / len(rows)))
    P('строк с любым идентификатором: %d (%.1f%%); без идентификатора: %d (%.1f%%)'
      % (n_any, 100 * n_any / len(rows), len(rows) - n_any, 100 * (len(rows) - n_any) / len(rows)))
    P('«зав. № б/н» и подобное: %d строк'
      % sum(1 for r in rows if re.search(r'зав\w*\.?\s*№*\s*б\s*/?\s*н', r['obekt'], re.I)))
    uniq = len(keycnt)
    dup_groups = sum(1 for v in keycnt.values() if v > 1)
    dup_rows = sum(v for v in keycnt.values() if v > 1)
    P('\nуникальных машин среди идентифицируемых строк: %d' % uniq)
    P('машин с более чем одним заключением: %d (%.1f%% машин)' % (dup_groups, 100 * dup_groups / uniq))
    P('строк, попавших в такие группы: %d' % dup_rows)
    P('максимум заключений на одну машину: %d' % max(keycnt.values()))
    P('распределение числа заключений на машину: %s'
      % sorted(collections.Counter(keycnt.values()).items()))
    P('\nверхняя оценка реального парка: %d машин + %d строк без номера = %d — %d'
      % (uniq, len(rows) - n_any, uniq, uniq + (len(rows) - n_any)))
    P('\nтоп машин по числу заключений:')
    for k, c in keycnt.most_common(10):
        P('  %d закл.  ИНН %s  %-38s  %s №%s'
          % (c, k[0], ent_name[k[0]][:38], k[1], k[2]))
    ex = keycnt.most_common(1)[0][0]
    P('\n  разворот самой «дублированной» машины (%s):' % str(ex))
    for e in enriched:
        if e['key'] == ex:
            P('    %s  %s  %s' % (e['row']['data'], e['row']['nomer'], e['row']['obekt'][:95]))
    # сколько предприятий раздуто дублями
    per_ent = collections.defaultdict(lambda: [0, 0])   # [строк, машин]
    for e in enriched:
        if e['key']:
            per_ent[e['row']['inn_zakazchika']][0] += 1
    seen = set()
    for e in enriched:
        if e['key'] and e['key'] not in seen:
            seen.add(e['key'])
            per_ent[e['row']['inn_zakazchika']][1] += 1
    infl = sorted(((v[0] / v[1], k, v) for k, v in per_ent.items() if v[1] >= 10), reverse=True)
    P('\n  предприятия с наибольшим раздуванием (строк на машину, парк >= 10 машин):')
    for ratio, inn, v in infl[:10]:
        P('    x%.2f  %s  %-40s  %d строк / %d машин' % (ratio, inn, ent_name[inn][:40], v[0], v[1]))

    # ══ 3. Реорганизации ═══════════════════════════════════════════════════
    P('\n' + '=' * 70 + '\n3. РЕОРГАНИЗАЦИИ (ОДИН ЗАВОД ПОД ДВУМЯ ИНН)\n' + '=' * 70)
    by_norm = collections.defaultdict(list)
    for inn, nm in ent_name.items():
        by_norm[norm_name(nm)].append(inn)
    ent_rows = collections.Counter(r['inn_zakazchika'] for r in rows)
    ent_srok = collections.defaultdict(collections.Counter)
    ent_last = {}
    for r in rows:
        ent_srok[r['inn_zakazchika']][r['srok']] += 1
        d = r['data']
        try:
            key = (d[6:10], d[3:5], d[0:2])
        except Exception:
            key = ('', '', '')
        if r['inn_zakazchika'] not in ent_last or key > ent_last[r['inn_zakazchika']][0]:
            ent_last[r['inn_zakazchika']] = (key, d)

    # общие заводские номера — независимая проверка «это тот же парк»
    zav_owners = collections.defaultdict(set)
    for e in enriched:
        if e['zav'] and len(e['zav']) >= 4:
            zav_owners[e['zav']].add(e['row']['inn_zakazchika'])

    def shared(a, b):
        return sum(1 for v in zav_owners.values() if a in v and b in v)

    def card(inn):
        s = ent_srok[inn]
        return ('%s  %-42s регион %s  заключений %d (действ.%d/истек.%d/просроч.%d), последнее %s'
                % (inn, ent_name[inn][:42], REGIONS.get(inn[:2], '?'), ent_rows[inn],
                   s['active'], s['expiring'], s['expired'], ent_last[inn][1]))

    P('\n3.1 Точное совпадение нормализованного названия при разных ИНН:')
    exact = [(k, v) for k, v in by_norm.items() if len(v) > 1 and k]
    for k, v in sorted(exact):
        P('\n  «%s»' % k)
        for inn in sorted(v, key=lambda i: -ent_rows[i]):
            P('    %s' % card(inn))
        pairs = [(v[i], v[j]) for i in range(len(v)) for j in range(i + 1, len(v))]
        for a, b in pairs:
            P('    общих заводских номеров (>=4 знака): %d;  регионы ИНН: %s / %s'
              % (shared(a, b), REGIONS.get(a[:2], '?'), REGIONS.get(b[:2], '?')))

    P('\n3.2 Близкие названия (difflib >= 0.86), кандидаты и однофамильцы:')
    keys = sorted(k for k in by_norm if k)
    for i in range(len(keys)):
        for j in range(i + 1, len(keys)):
            ka, kb = keys[i], keys[j]
            if abs(len(ka) - len(kb)) > 6:
                continue
            ratio = difflib.SequenceMatcher(None, ka, kb).ratio()
            if ratio < 0.86:
                continue
            a, b = by_norm[ka][0], by_norm[kb][0]
            P('  %.2f  %s | %s   (общих зав.№ %d)'
              % (ratio, ent_name[a][:40], ent_name[b][:40], shared(a, b)))

    P('\n3.3 Проверка обратным ходом — общие заводские номера у разных ИНН:')
    pairs = collections.Counter()
    for v in zav_owners.values():
        if len(v) > 1:
            v = sorted(v)
            for i in range(len(v)):
                for j in range(i + 1, len(v)):
                    pairs[(v[i], v[j])] += 1
    P('  пар ИНН с хотя бы одним общим номером: %d' % len(pairs))
    for (a, b), c in pairs.most_common(8):
        P('    %2d  %-38s | %s' % (c, ent_name[a][:38], ent_name[b][:38]))

    # ══ 4. ТУ против ЗС ════════════════════════════════════════════════════
    P('\n' + '=' * 70 + '\n4. ТУ ПРОТИВ ЗС\n' + '=' * 70)
    tips = collections.defaultdict(set)
    klasses = collections.defaultdict(set)
    for e in enriched:
        tips[e['row']['inn_zakazchika']].add(e['row']['tip'])
        klasses[e['row']['inn_zakazchika']].add(e['klass'])
    only_zs = [i for i, t in tips.items() if t == {'ЗС'}]
    only_tu = [i for i, t in tips.items() if t == {'ТУ'}]
    both = [i for i, t in tips.items() if len(t) > 1]
    P('предприятий только с ЗС: %d;  только с ТУ: %d;  и то и другое: %d'
      % (len(only_zs), len(only_tu), len(both)))
    P('\nсписок предприятий ТОЛЬКО с ЗС (слабые лиды):')
    for i in sorted(only_zs, key=lambda x: -ent_rows[x]):
        P('  %s' % card(i))
        for e in enriched:
            if e['row']['inn_zakazchika'] == i:
                P('      объект: %s' % e['row']['obekt'][:120])
                break
    no_mach = [i for i, k in klasses.items() if 'компрессор' not in k]
    P('\nболее строгая версия: предприятий, у которых НИ ОДНОЙ строки класса '
      '«компрессор»: %d' % len(no_mach))
    for i in sorted(no_mach, key=lambda x: -ent_rows[x])[:20]:
        P('  %s  [классы: %s]' % (card(i), sorted(klasses[i])))
    P('\nраспределение klass по tip: %s'
      % dict(collections.Counter((e['row']['tip'], e['klass']) for e in enriched)))
    P('klass итого: %s' % dict(collections.Counter(e['klass'] for e in enriched)))

    # ══ 5. География и отрасль ═════════════════════════════════════════════
    P('\n' + '=' * 70 + '\n5. ГЕОГРАФИЯ И ОТРАСЛЬ\n' + '=' * 70)
    P('Отдельной колонки региона в выгрузке нет. Считаем по первым двум цифрам ИНН —')
    P('это регион налоговой регистрации юрлица, а не адрес площадки.')
    reg_ent = collections.Counter(REGIONS.get(i[:2], 'код ' + i[:2]) for i in ent_name)
    reg_row = collections.Counter(REGIONS.get(r['inn_zakazchika'][:2], 'код ' + r['inn_zakazchika'][:2])
                                  for r in rows)
    P('\nрегионов представлено: %d' % len(reg_ent))
    P('%-42s %8s %10s' % ('регион (по ИНН)', 'предпр.', 'заключений'))
    for reg, c in reg_ent.most_common():
        P('%-42s %8d %10d' % (reg, c, reg_row[reg]))

    # честная проверка: у московских ИНН площадка часто в другом регионе
    place = re.compile(r'([А-ЯЁ][а-яё\-]+(?:ская|ский|цкая|цкий)\s+(?:обл|область|край)'
                       r'|Республик\w+\s+[А-ЯЁ][а-яё\-]+|ХМАО|ЯНАО|г\.\s?[А-ЯЁ][а-яё\-]+)')
    msk = [i for i in ent_name if i[:2] == '77']
    hits = 0
    ex_msk = []
    for i in msk:
        txts = ' '.join(r['obekt'] for r in rows if r['inn_zakazchika'] == i)
        m = place.findall(txts)
        m = [x for x in m if 'Москв' not in x]
        if m:
            hits += 1
            if len(ex_msk) < 8:
                ex_msk.append((ent_name[i][:38], collections.Counter(m).most_common(2)))
    P('\nпроверка смещения: предприятий с московским ИНН — %d; из них у %d в тексте объектов'
      % (len(msk), hits))
    P('упомянут другой регион, то есть площадка не в Москве. Примеры:')
    for n, m in ex_msk:
        P('  %-40s %s' % (n, m))

    P('\nотрасль (грубая раскладка по названию юрлица и тексту объектов):')
    ent_texts = collections.defaultdict(list)
    for r in rows:
        if len(ent_texts[r['inn_zakazchika']]) < 40:
            ent_texts[r['inn_zakazchika']].append(r['obekt'])
    ind = {i: industry_of(n, ent_texts[i]) for i, n in ent_name.items()}
    ind_ent = collections.Counter(ind.values())
    ind_row = collections.Counter(ind[r['inn_zakazchika']] for r in rows)
    P('%-38s %8s %10s' % ('отрасль', 'предпр.', 'заключений'))
    for k, c in ind_ent.most_common():
        P('%-38s %8d %10d' % (k, c, ind_row[k]))
    P('\nчто попало в «прочее / не определено»:')
    for i, n in ent_name.items():
        if ind[i].startswith('прочее'):
            P('  %s  %s' % (i, n[:60]))

    # ══ 6. Экспертные организации ══════════════════════════════════════════
    P('\n' + '=' * 70 + '\n6. ЭКСПЕРТНЫЕ ОРГАНИЗАЦИИ\n' + '=' * 70)
    eo_name = {}
    for r in rows:
        eo_name.setdefault(r['inn_eo'], r['ekspertnaya_org'])
    eo_rows = collections.Counter(r['inn_eo'] for r in rows)
    eo_ent = collections.defaultdict(set)
    for r in rows:
        eo_ent[r['inn_eo']].add(r['inn_zakazchika'])
    P('всего ЭО: %d; медиана заключений на ЭО: %d'
      % (len(eo_rows), sorted(eo_rows.values())[len(eo_rows) // 2]))
    P('ЭО с одним заключением: %d' % sum(1 for v in eo_rows.values() if v == 1))
    P('\nТоп-15 по числу заключений:')
    P('%-4s %-13s %-46s %8s %8s %s' % ('#', 'ИНН', 'экспертная организация', 'закл.', 'предпр.', 'регион ИНН'))
    for n, (inn, c) in enumerate(eo_rows.most_common(15), 1):
        P('%-4d %-13s %-46s %8d %8d %s'
          % (n, inn, eo_name[inn][:46], c, len(eo_ent[inn]), REGIONS.get(inn[:2], '?')))
    P('\nТоп-15 по числу обслуженных предприятий:')
    P('%-4s %-13s %-46s %8s %8s %s' % ('#', 'ИНН', 'экспертная организация', 'предпр.', 'закл.', 'регион ИНН'))
    for n, (inn, s) in enumerate(sorted(eo_ent.items(), key=lambda x: -len(x[1]))[:15], 1):
        P('%-4d %-13s %-46s %8d %8d %s'
          % (n, inn, eo_name[inn][:46], len(s), eo_rows[inn], REGIONS.get(inn[:2], '?')))
    top15 = [i for i, _ in eo_rows.most_common(15)]
    P('\nдоля топ-15 ЭО в заключениях: %.1f%%'
      % (100 * sum(eo_rows[i] for i in top15) / len(rows)))
    covered = set()
    for i in top15:
        covered |= eo_ent[i]
    P('предприятий, покрытых топ-15 ЭО: %d из %d (%.1f%%)'
      % (len(covered), len(ent_name), 100 * len(covered) / len(ent_name)))

    # ══ Запись очищенного CSV ══════════════════════════════════════════════
    fields = list(rows[0].keys()) + ['zav_nomer', 'klass', 'dubl']
    with open(DST, 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=fields, delimiter=';')
        w.writeheader()
        for e in enriched:
            d = dict(e['row'])
            d['zav_nomer'] = e['zav']
            d['klass'] = e['klass']
            d['dubl'] = e['dubl']
            w.writerow(d)
    P('\nЗаписано: %s (%d строк, %d колонок)' % (DST, len(enriched), len(fields)))
    P('dubl: %s' % dict(collections.Counter(e['dubl'] for e in enriched)))


if __name__ == '__main__':
    main()
