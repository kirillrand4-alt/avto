# -*- coding: utf-8 -*-
"""Факты о машинах из ПОТОКОВ реестра ЭПБ (глубина + ширина), а не из старой центробежной выгрузки.

ПОЧЕМУ ПЕРЕПИСАНО. Прежний разбор шёл по `VAZHNOE-3s-EPB-NASHI-MASHINY.csv` — выгрузке,
снятой под задачу о центробежных: 313 предприятий, это её потолок, а не реестра. Здесь вход —
`PARK-EPB-PO-INN-2S.jsonl` (полные списки заключений по ИНН) и `PARK-EPB-SHIROKIY-2S.jsonl`
(поиск по всей номенклатуре).

ШЕСТЬ ПРАВОК, КАЖДАЯ ИЗ ПРОВЕРКИ ГЛАЗАМИ (25 случайных ссылок, отчёт агента):
1. `UZEL` больше не якорится на начало строки. Реальные зачины разные: «на технические
   устройства: », «Техническое устройство – » (тире, не двоеточие), «№ 9-142-2014 »,
   «ЗАКЛЮЧЕНИЕ №C-0407-25 экспертизы … объекте ». Из-за якоря 2 303 строки (11,1 %)
   назывались машиной, а в объекте стояла деталь.
2. В словарь узлов добавлены `задвижка` и `охладитель` — на них ловились задвижка Ду 250 и
   охладитель газа.
3. «Компрессорная станция» больше не перебивает «компрессор», когда станция названа МЕСТОМ
   («компрессор К-500-61-1 … в компрессорной станции»): тип берётся по первому слову-машине.
4. `MARKA` допускает три и более ведущих цифр: «305ВП-40/3» терялось совсем (347 строк).
5. Модификация в хвосте не отрезается: «43ВЦ-160/9 М2».
6. Цитата 400 знаков вместо 220: на 220 ровно обрывались 7 487 строк, и в хвосте оставались
   номер ОПО, класс опасности и место установки.
"""
import csv, collections, html, json, os, re, sys, urllib.parse

L = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'engineers-lens')
POTOKI = [os.path.join(L, 'PARK-EPB-PO-INN-2S.jsonl'),
          os.path.join(L, 'PARK-EPB-SHIROKIY-2S.jsonl')]
VYHOD = os.path.join(L, 'PARK-FAKTY-2S-EPB-POLNYE.csv')
COLS = ['inn', 'predpriyatie', 'tip', 'marka_model', 'zavodskoy_nomer', 'sreda', 'data',
        'nomer_zaklucheniya', 'vyvod', 'srok_do', 'sila', 'klass', 'istochnik', 'ssylka', 'citata']

UZEL = re.compile(r'(холодильник|воздухоохладител|маслоохладител|охладител|теплообменник|'
                  r'трубопровод|маслоотделител|влагоотделител|сепаратор|фильтр|задвижк|'
                  r'предохранительн\w+ клапан|манометр|арматур|ресивер\w*\s+компрессор)', re.I)
TIPY = [
    ('генератор азота',      r'генератор\w*\s+азота|азотн\w+\s+(?:станц|установк|генератор)'),
    ('генератор кислорода',  r'генератор\w*\s+кислорода|кислородн\w+\s+(?:станц|установк)'),
    ('ВРУ',                  r'воздухоразделительн\w+|\bВРУ\b'),
    ('воздуходувка',         r'воздуходувк\w*|газодувк\w*|турбовоздуходувк\w*|нагнетател\w*'),
    ('МКС',                  r'\bМКС\b|мобильн\w+\s+компрессорн\w+|передвижн\w+\s+компрессорн\w+'),
    ('компрессор',           r'компрессор(?!н)\w*'),
    ('компрессорная станция', r'компрессорн\w+\s+станци\w+'),
    ('осушитель',            r'осушител\w*'),
    ('ресивер',              r'ресивер\w*|воздухосборник\w*'),
]
SREDY = [('азот', r'азот'), ('кислород', r'кислород'), ('аммиак', r'аммиак'),
         ('водород', r'водород'), ('природный газ', r'природн\w+\s+газ|метан'),
         ('воздух', r'воздух|пневмат')]
MARKA = re.compile(r'(?<![А-Яа-яA-Za-z0-9])'
                   r'([0-9]{0,3}[А-ЯA-Z]{1,4}[0-9А-ЯA-Z]{0,3}[-\s]?[0-9][0-9А-ЯA-Z/,.\-]{0,16}'
                   r'(?:\s?[А-ЯA-Z]{1,2}[0-9]{0,2})?)'
                   r'(?![а-яa-z])')
ZAVOD = re.compile(r'зав(?:одск\w*)?\.?\s*(?:№|N|номер)\s*([0-9A-ZА-Я\-/]{1,18})', re.I)
NE_MARKA = re.compile(r'^(ГОСТ|ТУ|ФНП|РД|СНИП|ПБ|№)', re.I)
CHUZHOY_NOMER = re.compile(r'(?:тех(?:н|нологическ\w+)?\.?\s*(?:№|индекс|N)|инв(?:ентарн\w+)?\.?\s*№|'
                           r'рег(?:истрационн\w+)?\.?\s*№|поз(?:иционн\w+)?\.?\s*№|зав\.?\s*№|'
                           r'заключение\s*№|цех\s*№|корпус\s*№|установка)\s*$', re.I)
# МАШИНА, НАЗВАННАЯ ПОСЛЕ ЭТИХ СЛОВ, — ЭТО МЕСТО, А НЕ ОБЪЕКТ ЭКСПЕРТИЗЫ. Проверено глазами:
# «Баллон для воздуха уменьшенной длины, зав. №1273, применяемое на опасном производственном
# объекте … компрессорная станция» — экспертиза на БАЛЛОН, а станция лишь адрес установки.
MESTO = re.compile(r'применяем\w+\s+на|на\s+опасном\s+производственном\s+объекте|'
                   r'расположенн\w+\s+(?:в|на)|установленн\w+\s+(?:в|на)|'
                   r'принадлежащ\w+|входящ\w+\s+в\s+состав', re.I)

SLOVO_TIPA = re.compile(r'(компрессор\w*|воздуходувк\w*|газодувк\w*|нагнетател\w*|'
                        r'турбокомпрессор\w*|ВРУ|ресивер\w*|осушител\w*)', re.I)


# МНЕМОНИКИ HTML РАСКОДИРОВАТЬ ДО РАЗБОРА. Находка 1-й сессии: счётчики на `&quot;` не
# спотыкаются — для них это обычный текст, база «здорова», а продавец получил бы
# «принадлежащий тресту &quot;Норильскшахтсервис&quot;». У меня таких строк 7 959 из 20 488.
# Раскодировать надо ДО разбора: иначе `&quot;` попадает внутрь марки и ломает шаблон.
def razobrat(obekt):
    t = ' '.join(html.unescape(obekt or '').split())
    # Тип — по ПЕРВОМУ встреченному слову-машине, а не по порядку списка: иначе «компрессорная
    # станция», названная местом установки, перебивает сам компрессор.
    najd = [(m.start(), n) for n, p in TIPY for m in [re.search(p, t, re.I)] if m]
    mesto = MESTO.search(t)
    if mesto:
        # оставляем только те слова-машины, что стоят ДО указания места
        do_mesta = [x for x in najd if x[0] < mesto.start()]
        najd = do_mesta if do_mesta else []
    tip = min(najd)[1] if najd else ''
    if tip:
        u = UZEL.search(t)
        # Узел засчитывается, только если деталь названа РАНЬШЕ машины: «холодильник
        # компрессора» — узел, «компрессор с холодильником» — машина.
        if u and u.start() < min(najd)[0]:
            tip = 'узел: ' + tip
    sreda = next((n for n, p in SREDY if re.search(p, t, re.I)), '')
    z = ZAVOD.search(t)
    zav = z.group(1) if z else ''
    if re.fullmatch(r'б/?н|бн|отсутств\w*|-+', zav, re.I):
        zav = ''
    marka = ''
    st = SLOVO_TIPA.search(t)
    if st:
        hvost = t[st.end():st.end() + 70]
        for m in MARKA.finditer(hvost):
            kand = m.group(1).strip(' ,.')
            if len(kand) >= 3 and not NE_MARKA.match(kand) \
                    and not CHUZHOY_NOMER.search(hvost[:m.start()]):
                marka = kand
                break
    return tip, sreda, zav, marka


def main():
    vidno, out = set(), []
    sch = collections.Counter()
    for p in POTOKI:
        if not os.path.exists(p):
            continue
        for ln in open(p, encoding='utf-8'):
            try:
                z = json.loads(ln)
            except json.JSONDecodeError:
                continue
            for r in (z.get('stroki') or []):
                ob = r.get('obekt') or ''
                tip, sreda, zav, marka = razobrat(ob)
                if not tip:
                    sch['объект не называет нашу машину'] += 1
                    continue
                # КЛЮЧ ДЕДУПА ПО ОБЩЕМУ РЕШЕНИЮ: inn + тип + марка + заводской номер + дата.
                # Заводской номер обязателен в ключе: два одинаковых компрессора на одном
                # заводе — две машины и две продажи, схлопывать их нельзя.
                k = (r.get('inn'), tip, marka, zav, r.get('data'), r.get('nomer'))
                if k in vidno:
                    sch['повтор'] += 1
                    continue
                vidno.add(k)
                sch['фактов'] += 1
                sch['  с заводским номером' if zav else '  без заводского номера'] += 1
                sch['  узел' if tip.startswith('узел') else '  машина'] += 1
                out.append({'inn': r.get('inn'), 'predpriyatie': html.unescape(r.get('predpriyatie') or '')[:70],
                            'tip': tip, 'marka_model': marka, 'zavodskoy_nomer': zav,
                            'sreda': sreda, 'data': r.get('data') or '',
                            'nomer_zaklucheniya': r.get('nomer') or '',
                            'vyvod': r.get('vyvod') or '', 'srok_do': r.get('deystvuet_do') or '',
                            'sila': 1, 'klass': 'надзорная запись: заключение ЭПБ',
                            'istochnik': (r.get('ekspertnaya_org') or '')[:60],
                            # ССЫЛКА ОБЯЗАНА ВЕСТИ НА САМО ДОКАЗАТЕЛЬСТВО, А НЕ НА СПИСОК.
                            # Широкий проход клал `/conclusions?exploiter=<ИНН>` — это перечень
                            # всех заключений завода, по нему конкретную машину не найти.
                            # Номер заключения в строке есть всегда, значит адрес карточки
                            # строится точно: /conclusion/<номер>. Проверено на пяти случайных
                            # строках глазами по требованию владельца.
                            'ssylka': (f'https://monitor-pb.ru/conclusion/'
                                       f'{urllib.parse.quote(r["nomer"])}'
                                       if (r.get('nomer') or '').strip()
                                       else (r.get('ssylka') or '')),
                            'citata': ' '.join(html.unescape(ob).split())[:400]})
    with open(VYHOD, 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=COLS, delimiter=';', extrasaction='ignore')
        w.writeheader(); w.writerows(out)
    for k, v in sch.most_common():
        print(f'  {v:>8}  {k}', file=sys.stderr)
    print(f'предприятий: {len({x["inn"] for x in out})}', file=sys.stderr)
    print(f'типы: {dict(collections.Counter(x["tip"] for x in out).most_common(12))}', file=sys.stderr)
    print(f'без ссылки: {sum(1 for x in out if not x["ssylka"])}', file=sys.stderr)
    print(f'→ {VYHOD}', file=sys.stderr)


main()
