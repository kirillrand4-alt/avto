# -*- coding: utf-8 -*-
"""Что именно доказано по каждому предприятию: машина или не машина, центробежная или нет.

Вопрос владельца, с которого всё началось: «там доказан именно центробежный компрессор?».
Проверил — и нет. В сводке трёх состояний перемешаны три разные вещи, а колонка `sostoyaniy`
их не различала:

1. **объект вообще не машина.** Реестр заключений ЭПБ содержит экспертизы на газопроводы,
   здания, резервуары, краны. Отбор шёл по обозначению марки из текста, и обозначение вида
   `Г 1.1`, `ГРП 28`, `Л-35/11-1000` проходило фильтр. Замер по 38 960 фактам «есть»:
   про машину 14 869, заведомо не про машину 14 841, непонятно 9 250. В пересчёте на
   предприятия: у 667 есть хоть один факт про машину, а **1 461 предприятие держится ТОЛЬКО
   фактами про газопроводы и сооружения**;
2. **машина есть, но тип не назван.** «Компрессор» без указания вида — это может быть поршневой
   или винтовой, то есть не наш;
3. **машина центробежная** — прямое слово в тексте (центробежный, турбокомпрессор,
   воздуходувка, нагнетатель) или обозначение серии, которая центробежной является по
   определению (К-, ЦК-, ТК-, ГТК-).

Отсюда две новые колонки в каждом факте и в сводке по предприятиям, и очередь для продажников
строится по ним, а не по числу состояний.

Порядок строгости намеренный: сначала «это вообще машина», потом «какая». Утверждать
центробежность по обозначению марки в заключении про газопровод нельзя, даже если обозначение
похоже.

Использование:
    python3 tip_mashiny.py
"""
import csv
import os
import re
from collections import defaultdict

csv.field_size_limit(10 ** 7)
BAZA = os.path.dirname(os.path.abspath(__file__))
L = os.path.join(BAZA, 'engineers-lens')
FAKTY = os.path.join(L, 'SVOD-tri-sostoyaniya.csv')
PO_PRED = os.path.join(L, 'SVOD-POLNYY-po-predpriyatiyam.csv')
OCHERED = os.path.join(L, 'OCHERED-centrobezhnye.csv')

# Объект экспертизы или закупки — заведомо НЕ машина.
NE_MASHINA = re.compile(r'газопровод|трубопровод|сооружени|здани|резервуар|ёмкост|емкост|'
                        r'кран\b|мостов|эстакад|дымов|труб[аы]\b|сосуд|котёл|котел\b|печь|печи\b|'
                        r'цистерн|вагон|путепровод|склад|площадк|градирн|скважин|дорог|кабел', re.I)
# Объект — машина нашего рода.
MASHINA = re.compile(r'компрессор|воздуходувк|нагнетател|турбоагрегат|турбокомпрессор|турбовозду|'
                     r'газоперекачива|\bГПА\b|дожимн|компрессорн', re.I)
# Прямое слово о центробежности.
CENTR = re.compile(r'центробежн|турбокомпрессор|турбовозду|воздуходувк|турбоагрегат|нагнетател|'
                   r'осевой\s+компрессор', re.I)
# Прямое слово о НЕ нашем типе.
NE_NASH_TIP = re.compile(r'поршнев|винтов|спиральн|мембранн|шестерён|роторно-пластинч|'
                         r'плунжерн|диафрагменн', re.I)
# Серии, центробежные по определению. Требуем цифру после, иначе «К» ловит что угодно.
CENTR_SERIYA = re.compile(r'^(?:ЦК|ТК|КТК|ГТК|КЦ|ТКА|НЦ|ЦНГ|К)[\s\-]?\d', re.I)

# --- НЕ НАША МАШИНА, хотя слова похожи. Вопрос владельца «это точно воздушные центробежные?»
# вскрыл пять классов примеси; замер по 17 708 фактам «доказанная центробежная»: 2 801 факт,
# то есть каждый шестой. Порядок проверок важен: сначала отсев, потом объявление центробежности.
NE_NASHA = [
    # «турбоагрегат» на ТЭЦ это паровая турбина с генератором, а не компрессор. Самый крупный
    # класс примеси: 2 067 фактов. Пример: «Капитальный ремонт турбоагрегата ПТ 60-90/13».
    ('паровая турбина, не компрессор',
     re.compile(r'турбоагрегат\w*\s*(?:типа\s*)?(?:ПТ|Т|ПР|Р|К)[\s\-]?\d+[\s\-]?\d*/|'
                r'паров\w+\s+турбин|турбогенератор|теплофикацион\w+\s+турбин', re.I)),
    # Садовая и ранцевая воздуходувка — 421 факт. Слово то же, машина другая на три порядка.
    ('садовый инструмент, не машина',
     re.compile(r'бензинов\w+\s+воздуходувк|ранцев|садов\w+\s+воздуходувк|воздуходувк\w*[-\s]пылесос|'
                r'воздуходувк\w+\s+для\s+уборки|уборки\s+территории|аккумуляторн\w+\s+воздуходувк|'
                # «Поставка уборочной техники (воздуходувка и снегоуборщик) для содержания
                # территории» — примесь, которую прежний шаблон не ловил: он требовал слов
                # «бензиновая» или «ранцевая», а тут вид назван через род «уборочная техника».
                r'уборочн\w+\s+техник|содержани\w+\s+территории|снегоубор|газонокос|бензокос|'
                r'благоустройств\w+\s+территории|парк\w*\s+и\s+сквер', re.I)),
    # Вихревая (боковой канал) и РУТС (роторная, объёмного действия) — принцип не центробежный.
    # Замер по панели продажников: 142 факта числились центробежными, а в цитате стоит
    # «Поставка воздуходувки Рутс ERB-100» или «вихревой промышленной воздуходувки».
    ('вихревая или роторная воздуходувка, принцип не центробежный',
     re.compile(r'вихрев\w+\s+(?:воздуходувк|нагнетател)|\bрутс\b|\broots\b|'
                r'роторн\w+\s+(?:воздуходувк|нагнетател|компрессор)|'
                r'объ[её]мн\w+\s+(?:воздуходувк|нагнетател|компрессор)', re.I)),
    # Центробежный НАСОС и масляные агрегаты обвязки — 145 фактов.
    ('центробежный насос, не компрессор',
     re.compile(r'центробежн\w+\s+насос|электронасос|насосн\w+\s+агрегат|маслян\w+\s+насос|'
                r'\bЭЦВ\b|\bЦНС\b', re.I)),
    # Вентилятор и дымосос: «воздуходувка на базе радиального вентилятора» — не наша машина.
    ('вентилятор или дымосос',
     re.compile(r'на\s+базе\s+(?:центробежн\w+\s+)?(?:радиальн\w+\s+)?вентилятор|дымосос|'
                r'вентилятор\w*\s+тип[аи]?\s', re.I)),
]

# Среда. Для продавца воздушных машин это второй по важности признак после центробежности.
# Воздухоразделительная установка считается воздухом: на входе у неё атмосферный воздух.
VOZDUH = re.compile(r'воздух|воздуходувк|турбовозду|пневмо|аэротенк|аэраци|'
                    r'воздухоразделительн|\bВРУ\b|компрессор\w*\s+воздушн', re.I)
GAZ = re.compile(r'газоперекачива|\bГПА\b|природн\w+\s+газ|попутн\w+\s+газ|газов\w+\s+компрессор|'
                 r'этилен|аммиак|водород|сероводород|нефтян\w+\s+газ|дожимн\w+\s+компрессорн|'
                 r'\bДКС\b|\bУКПГ\b|хладагент|фреон|пропан', re.I)


def sreda_mashiny(marki, tekst):
    t = f'{marki} {tekst}'[:1200]
    v, g = bool(VOZDUH.search(t)), bool(GAZ.search(t))
    if v and g:
        return 'воздух и газ названы оба'
    if v:
        return 'воздух'
    if g:
        return 'газ или иная среда'
    return 'среда не названа'


def razobrat(marki, tekst):
    """Вернуть (объект, тип). Порядок строгий: отсев чужого → «машина ли» → «какая»."""
    t = f'{marki} {tekst}'[:1200]
    # Отсев идёт ПЕРВЫМ. Иначе «воздуходувка бензиновая ранцевая» объявляется центробежной
    # по слову «воздуходувка», а «турбоагрегат ПТ 60-90/13» — по слову «турбоагрегат».
    for imya, rx in NE_NASHA:
        if rx.search(t):
            return 'не наша машина', imya
    est_mashina = bool(MASHINA.search(t))
    if est_mashina:
        obekt = 'машина'
    elif NE_MASHINA.search(t):
        obekt = 'не машина'
    else:
        obekt = 'не установлено'
    if obekt != 'машина':
        # Центробежность объявляем только там, где объект — машина. Обозначение серии в
        # заключении про газопровод доказательством машины не является.
        return obekt, 'не применимо' if obekt == 'не машина' else 'не установлен'
    if CENTR.search(t):
        return obekt, 'центробежная'
    if any(CENTR_SERIYA.match(m.strip()) for m in (marki or '').split('|') if m.strip()):
        return obekt, 'центробежная по серии'
    if NE_NASH_TIP.search(t):
        return obekt, 'поршневая или винтовая'
    return obekt, 'тип не установлен'


def main():
    fakty = list(csv.DictReader(open(FAKTY, encoding='utf-8-sig'), delimiter=';'))
    po_inn = defaultdict(lambda: {'obekt': set(), 'tip': set(), 'sost': set(), 'sreda': set()})
    schet = defaultdict(int)
    for x in fakty:
        o, t = razobrat(x.get('marki') or '', x.get('tekst') or '')
        x['obekt'] = o
        x['tip_mashiny'] = t
        x['sreda_mashiny'] = sreda_mashiny(x.get('marki') or '', x.get('tekst') or '')
        schet[f'{x["sostoyanie"]} | {o} | {t}'] += 1
        d = po_inn[x['inn']]
        d['obekt'].add(o)
        d['tip'].add(t)
        d['sost'].add(x['sostoyanie'])
        if t in ('центробежная', 'центробежная по серии'):
            d['sreda'].add(x['sreda_mashiny'])

    cols = list(fakty[0].keys())
    with open(FAKTY, 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=cols, delimiter=';', extrasaction='ignore')
        w.writeheader()
        for x in fakty:
            w.writerow(x)

    DOKAZANO = {'центробежная', 'центробежная по серии'}
    SILNYE = {'есть', 'покупает', 'планирует', 'планировал'}
    pred = list(csv.DictReader(open(PO_PRED, encoding='utf-8-sig'), delimiter=';'))
    novye = ['mashina_dokazana', 'centrobezhnost_dokazana', 'tipy_mashin', 'sreda_dokazana']
    pcols = list(pred[0].keys()) + [c for c in novye if c not in pred[0]]
    for r in pred:
        d = po_inn.get(r['inn'])
        if not d:
            r['mashina_dokazana'] = r['centrobezhnost_dokazana'] = r['tipy_mashin'] = ''
            r['sreda_dokazana'] = ''
            continue
        silnoe = d['sost'] & SILNYE
        r['mashina_dokazana'] = '1' if ('машина' in d['obekt'] and silnoe) else ''
        r['centrobezhnost_dokazana'] = '1' if (d['tip'] & DOKAZANO and silnoe) else ''
        # сильное свидетельство печатаем первым: иначе в узкой колонке видно «не установлен»,
        # а «центробежная» уезжает за обрез — и строка читается наоборот тому, что доказано
        poryadok = {'центробежная': 0, 'центробежная по серии': 1, 'поршневая или винтовая': 2,
                    'тип не установлен': 3, 'не установлен': 4}
        r['tipy_mashin'] = ' | '.join(sorted(d['tip'] - {'не применимо'},
                                             key=lambda x: poryadok.get(x, 9)))[:80]
        # среда: воздух важнее всего, потом «оба названы», потом газ
        ps = {'воздух': 0, 'воздух и газ названы оба': 1, 'среда не названа': 2,
              'газ или иная среда': 3}
        r['sreda_dokazana'] = (sorted(d['sreda'], key=lambda x: ps.get(x, 9))[0]
                               if d['sreda'] else '')
    with open(PO_PRED, 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=pcols, delimiter=';', extrasaction='ignore')
        w.writeheader()
        for r in pred:
            w.writerow(r)

    # очередь: центробежность доказана, сверху те, у кого уже есть люди и телефоны
    och = [r for r in pred if r['centrobezhnost_dokazana'] == '1']

    def ves(x):
        # воздух наверх: правило владельца «воздух важнее газа»
        return (1 if x.get('sreda_dokazana') in ('воздух', 'воздух и газ названы оба') else 0,
                int(x.get('lyudej_tehnicheskih') or 0), 1 if x.get('telefony_predpriyatiya') else 0,
                1 if x.get('sayt') else 0, int(x.get('sostoyaniy') or 0))
    ocols = ['inn', 'predpriyatie', 'tipy_mashin', 'sreda_dokazana', 'marki', 'sostoyaniy', 'est', 'pokupaet',
             'planiruet', 'srok_sluzhby', 'vyvod_ekspertizy', 'data_zakluchenia', 'data_zakupki',
             'region', 'sayt', 'telefony_predpriyatiya', 'luchshaya_pochta', 'lyudej_tehnicheskih',
             'lyudej_s_telefonom', 'lyudi_podrobno', 'chego_ne_hvataet']
    with open(OCHERED, 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=ocols, delimiter=';', extrasaction='ignore')
        w.writeheader()
        for r in sorted(och, key=ves, reverse=True):
            w.writerow(r)

    # --- отчёт числами ИЗ ЗАПИСАННЫХ ФАЙЛОВ ---
    pf = list(csv.DictReader(open(FAKTY, encoding='utf-8-sig'), delimiter=';'))
    pp = list(csv.DictReader(open(PO_PRED, encoding='utf-8-sig'), delimiter=';'))
    po = list(csv.DictReader(open(OCHERED, encoding='utf-8-sig'), delimiter=';'))
    print(f'фактов: {len(pf)}')
    for k in sorted(schet, key=lambda k: -schet[k])[:12]:
        print(f'   {schet[k]:>6}  {k}')
    silnye = [r for r in pp if (r.get('sostoyaniy') or '0') != '0']
    print(f'\nпредприятий в сводке: {len(pp)}')
    print(f'  с сильным состоянием (есть/покупает/планирует): {len(silnye)}')
    print(f'    из них МАШИНА доказана:            {sum(1 for r in silnye if r["mashina_dokazana"])}')
    print(f'    из них ЦЕНТРОБЕЖНОСТЬ доказана:    {sum(1 for r in silnye if r["centrobezhnost_dokazana"])}')
    from collections import Counter as _C
    print('  среда у центробежных предприятий:',
          dict(_C(r['sreda_dokazana'] for r in pp if r['centrobezhnost_dokazana'])))
    print(f'  очередь центробежных → {len(po)} строк')
    print(f'    из них ВОЗДУХ: {sum(1 for r in po if r["sreda_dokazana"].startswith("воздух"))}')
    print(f'    из них с техническим человеком: {sum(1 for r in po if (r["lyudej_tehnicheskih"] or "0") != "0")}')
    print(f'    из них с телефоном предприятия: {sum(1 for r in po if r["telefony_predpriyatiya"])}')
    print(f'    из них без сайта:               {sum(1 for r in po if not r["sayt"])}')
    print(f'→ {OCHERED}')


if __name__ == '__main__':
    main()
