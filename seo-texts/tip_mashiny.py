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


def razobrat(marki, tekst):
    """Вернуть (объект, тип). Порядок строгий: сначала «машина ли», потом «какая»."""
    t = f'{marki} {tekst}'[:1200]
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
    po_inn = defaultdict(lambda: {'obekt': set(), 'tip': set(), 'sost': set()})
    schet = defaultdict(int)
    for x in fakty:
        o, t = razobrat(x.get('marki') or '', x.get('tekst') or '')
        x['obekt'] = o
        x['tip_mashiny'] = t
        schet[f'{x["sostoyanie"]} | {o} | {t}'] += 1
        d = po_inn[x['inn']]
        d['obekt'].add(o)
        d['tip'].add(t)
        d['sost'].add(x['sostoyanie'])

    cols = list(fakty[0].keys())
    with open(FAKTY, 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=cols, delimiter=';', extrasaction='ignore')
        w.writeheader()
        for x in fakty:
            w.writerow(x)

    DOKAZANO = {'центробежная', 'центробежная по серии'}
    SILNYE = {'есть', 'покупает', 'планирует', 'планировал'}
    pred = list(csv.DictReader(open(PO_PRED, encoding='utf-8-sig'), delimiter=';'))
    novye = ['mashina_dokazana', 'centrobezhnost_dokazana', 'tipy_mashin']
    pcols = list(pred[0].keys()) + [c for c in novye if c not in pred[0]]
    for r in pred:
        d = po_inn.get(r['inn'])
        if not d:
            r['mashina_dokazana'] = r['centrobezhnost_dokazana'] = r['tipy_mashin'] = ''
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
    with open(PO_PRED, 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=pcols, delimiter=';', extrasaction='ignore')
        w.writeheader()
        for r in pred:
            w.writerow(r)

    # очередь: центробежность доказана, сверху те, у кого уже есть люди и телефоны
    och = [r for r in pred if r['centrobezhnost_dokazana'] == '1']

    def ves(x):
        return (int(x.get('lyudej_tehnicheskih') or 0), 1 if x.get('telefony_predpriyatiya') else 0,
                1 if x.get('sayt') else 0, int(x.get('sostoyaniy') or 0))
    ocols = ['inn', 'predpriyatie', 'tipy_mashin', 'marki', 'sostoyaniy', 'est', 'pokupaet',
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
    print(f'  очередь центробежных → {len(po)} строк')
    print(f'    из них с техническим человеком: {sum(1 for r in po if (r["lyudej_tehnicheskih"] or "0") != "0")}')
    print(f'    из них с телефоном предприятия: {sum(1 for r in po if r["telefony_predpriyatiya"])}')
    print(f'    из них без сайта:               {sum(1 for r in po if not r["sayt"])}')
    print(f'→ {OCHERED}')


if __name__ == '__main__':
    main()
