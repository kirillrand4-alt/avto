# -*- coding: utf-8 -*-
"""ЭПБ → факты о машине. Из объекта заключения вынимаются тип, марка и ЗАВОДСКОЙ НОМЕР —
единственный ключ, отличающий машину от такой же соседней; больше его не даёт ни один источник.

РИСК, ПРОВЕРЕННЫЙ ДО РАЗБОРА: в файле ДВЕ колонки ИНН. Проверено на живых данных —
`inn` это заказчик (АО «НАК «АЗОТ», АО «АНХК»), `inn_eo` это экспертная организация
(«Русская лаборатория», ПАО «НОРЭ»). Склейка по `inn_eo` дала бы базу про лаборатории.
"""
import csv, re, sys, os, collections

csv.field_size_limit(10 ** 7)
L = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'engineers-lens')
VHOD = sys.argv[1] if len(sys.argv) > 1 else '/tmp/claude-0/-home-user-avto/520847fd-7699-5483-869b-cf6d49851f67/scratchpad/VAZHNOE-3s-EPB-NASHI-MASHINY.csv'
VYHOD = os.path.join(L, 'PARK-FAKTY-2S-EPB.csv')
COLS = ['inn', 'predpriyatie', 'tip', 'marka_model', 'zavodskoy_nomer', 'sreda', 'data',
        'srok_do', 'status_sroka', 'sila', 'klass', 'istochnik', 'ssylka', 'citata']

# ТИП МАШИНЫ. Порядок важен: «воздуходувка» проверяется до «компрессор», иначе
# «турбовоздуходувка компрессорной станции» уйдёт в компрессоры.
# ПРОВЕРЕНО ГЛАЗАМИ НА ДЕСЯТИ СЛУЧАЙНЫХ, И ЭТО ИЗМЕНИЛО РАЗБОР. Первая версия объявляла
# компрессором «Холодильник второй ступени компрессора ВК-2», «Воздухоохладитель
# турбокомпрессора К-350» и «Технологический трубопровод нагнетания 1 ступени компрессора».
# Это УЗЛЫ машины: они доказывают, что компрессор на заводе есть, но сами компрессором не
# являются. Отдельный тип, а не отсев: продавать узел нельзя, а доказательство он даёт.
UZEL = re.compile(r'^\s*(?:заключение[^:]{0,80}:\s*)?(?:техническое устройство:\s*)?'
                  r'(холодильник|воздухоохладител|маслоохладител|теплообменник|'
                  r'трубопровод|маслоотделител|влагоотделител|сепаратор|фильтр|'
                  r'предохранительн\w+ клапан|манометр|арматур)', re.I)

TIPY = [
    ('генератор азота',      r'генератор\w*\s+азота|азотн\w+\s+(?:станц|установк|генератор)'),
    ('генератор кислорода',  r'генератор\w*\s+кислорода|кислородн\w+\s+(?:станц|установк)'),
    ('ВРУ',                  r'воздухоразделительн\w+|\bВРУ\b'),
    ('воздуходувка',         r'воздуходувк\w*|газодувк\w*|турбовоздуходувк\w*|нагнетател\w*'),
    ('МКС',                  r'\bМКС\b|мобильн\w+\s+компрессорн\w+|передвижн\w+\s+компрессорн\w+'),
    ('компрессорная станция', r'компрессорн\w+\s+станци\w+'),
    ('компрессор',           r'компрессор\w*'),
    ('ресивер',              r'ресивер\w*|воздухосборник\w*'),
    ('осушитель',            r'осушител\w*'),
]
SREDY = [('азот', r'азот'), ('кислород', r'кислород'), ('аммиак', r'аммиак'),
         ('водород', r'водород'), ('природный газ', r'природн\w+\s+газ|метан'),
         ('воздух', r'воздух|пневмат')]
# МАРКА: буквенно-цифровое обозначение. Заслон «буква+число без бренда» — требуем
# минимум две буквы ИЛИ цифру внутри буквенной группы, и длину от 3 знаков.
# ОТЕЧЕСТВЕННЫЕ ОБОЗНАЧЕНИЯ НАЧИНАЮТСЯ С ЦИФРЫ: 4ВМ10-100/8, 2ГМ16-24/40-60С, 6ВВ-9/9,
# 3ГП-5/220, 43ВЦ-160. Первая версия требовала букву в начале и теряла их все — а по моему
# же замеру отечественных форм 1 772 против 966 импортных, то есть терялось большинство.
# Односимвольная буквенная часть тоже бывает: К-350, ФВ-6, ТВ-175.
MARKA = re.compile(r'(?<![А-Яа-яA-Za-z0-9])'
                   r'([0-9]{0,2}[А-ЯA-Z]{1,4}[0-9А-ЯA-Z]{0,3}[-\s]?[0-9][0-9А-ЯA-Z/,.\-]{0,16})'
                   r'(?![а-яa-z])')
ZAVOD = re.compile(r'зав(?:одск\w*)?\.?\s*(?:№|N|номер)\s*([0-9A-ZА-Я\-/]{1,18})', re.I)
NE_MARKA = re.compile(r'^(ГОСТ|ТУ|ФНП|РД|СНИП|ПБ|№)', re.I)


# МАРКА БЕРЁТСЯ СРАЗУ ЗА СЛОВОМ ТИПА, А НЕ ПЕРВОЙ ПОПАВШЕЙСЯ. Первая версия у
# «Поршневой компрессор 2ГМ16-24/40-60С, тех.№ ПК-102» брала ПК-102 (технологический
# номер), у «Воздухоохладитель турбокомпрессора К-350» — номер заключения А11-00054-0004,
# а у «площадка извлечения золота ЗИФ-1,2,3» — название фабрики.
CHUZHOY_NOMER = re.compile(r'(?:тех(?:н|нологическ\w+)?\.?\s*(?:№|индекс|N)|инв(?:ентарн\w+)?\.?\s*№|'
                           r'рег(?:истрационн\w+)?\.?\s*№|поз(?:иционн\w+)?\.?\s*№|зав\.?\s*№|'
                           r'заключение\s*№|цех\s*№|корпус\s*№|установка)\s*$', re.I)
SLOVO_TIPA = re.compile(r'(компрессор\w*|воздуходувк\w*|газодувк\w*|нагнетател\w*|'
                        r'турбокомпрессор\w*|ВРУ|ресивер\w*|осушител\w*)', re.I)


def razobrat(obekt):
    t = ' '.join((obekt or '').split())
    tip = next((n for n, p in TIPY if re.search(p, t, re.I)), '')
    if tip and UZEL.match(t):
        tip = 'узел ' + tip
    sreda = next((n for n, p in SREDY if re.search(p, t, re.I)), '')
    z = ZAVOD.search(t)
    zav = z.group(1) if z else ''
    if re.fullmatch(r'б/?н|бн|отсутств\w*|-+', zav, re.I):
        zav = ''          # «зав. № б/н» это ОТСУТСТВИЕ номера, а не номер
    marka = ''
    st = SLOVO_TIPA.search(t)
    if st:
        hvost = t[st.end():st.end() + 60]
        for m in MARKA.finditer(hvost):
            kand = m.group(1).strip(' ,.')
            do = hvost[:m.start()]
            if len(kand) >= 3 and not NE_MARKA.match(kand) and not CHUZHOY_NOMER.search(do):
                marka = kand
                break
    return tip, sreda, zav, marka


def main():
    rows = list(csv.DictReader(open(VHOD, encoding='utf-8-sig'), delimiter=';'))
    sch = collections.Counter()
    out = []
    for r in rows:
        tip, sreda, zav, marka = razobrat(r.get('obekt'))
        if not tip:
            sch['объект не называет нашу машину'] += 1
            continue
        srok = (r.get('deystvuet_do') or '').strip()
        # СРОК: сравниваем как даты, а не как строки. Формат в файле дд.мм.гггг.
        st = ''
        m = re.match(r'(\d{2})\.(\d{2})\.(\d{4})', srok)
        if m:
            st = 'истёк' if (m.group(3), m.group(2), m.group(1)) < ('2026', '08', '09') else 'действует'
        sch['фактов'] += 1
        sch['  с заводским номером' if zav else '  БЕЗ заводского номера'] += 1
        if st: sch['  срок ' + st] += 1
        out.append({'inn': r['inn'], 'predpriyatie': (r.get('predpriyatie') or '')[:70],
                    'tip': tip, 'marka_model': marka, 'zavodskoy_nomer': zav, 'sreda': sreda,
                    'data': (r.get('data') or ''), 'srok_do': srok, 'status_sroka': st,
                    'sila': 1, 'klass': 'надзорная запись: заключение ЭПБ',
                    'istochnik': (r.get('ekspertnaya_org') or '')[:60],
                    'ssylka': (r.get('ssylka') or ''),
                    'citata': ' '.join((r.get('obekt') or '').split())[:220]})
    with open(VYHOD, 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=COLS, delimiter=';', extrasaction='ignore')
        w.writeheader(); w.writerows(out)
    for k, v in sch.most_common():
        print(f'  {v:>7}  {k}', file=sys.stderr)
    print(f'предприятий: {len({x["inn"] for x in out})}', file=sys.stderr)
    print(f'типы: {dict(collections.Counter(x["tip"] for x in out).most_common(9))}', file=sys.stderr)
    print(f'→ {VYHOD}', file=sys.stderr)


main()
