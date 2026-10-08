# -*- coding: utf-8 -*-
"""Разделить базу (листы «Компании» и «Контакты») на 2 честные части (владелец 08.10).

Честно = у обеих частей поровну:
  компаний; компаний с номером покупателя оборудования; с номером ЛПР; с любым номером; мобильных;
  суммарной выручки; по каждому сегменту; «есть контакт в Битрикс».
Компании одного холдинга (общий номер или общий сайт) идут в одну часть — чтобы два менеджера не
звонили в один холдинг. Жадно: кластеры от самых ценных к менее ценным, каждый — в ту часть,
где перекос по всем метрикам выходит меньше.

    python razdelit_popolam.py <in.xlsx> <out1.xlsx> <out2.xlsx>
"""
import collections
import json
import re
import sys

from openpyxl import load_workbook


def строки(ws):
    rr = list(ws.iter_rows(values_only=True))
    return [dict(zip(rr[0], r)) for r in rr[1:]]


def хост(u):
    u = re.sub(r'^[a-z]+://', '', (u or '').strip().lower()).split('/')[0]
    ч = (u[4:] if u.startswith('www.') else u).split('.')
    return '.'.join(ч[-2:]) if len(ч) >= 2 else ''


def main(п_in, п1, п2):
    wb = load_workbook(п_in, read_only=True)
    комп = строки(wb['Компании'])
    конт = строки(wb['Контакты'])
    wb.close()
    # кластеры: общий номер или общий сайт
    родитель = {}

    def корень(x):
        while родитель.setdefault(x, x) != x:
            родитель[x] = родитель[родитель[x]]
            x = родитель[x]
        return x

    def слить(a, b):
        родитель[корень(a)] = корень(b)
    по_номеру = collections.defaultdict(set)
    for r in конт:
        н = r.get('Мобильный') or r.get('Рабочий')
        if н:
            по_номеру[re.sub(r'\s*доб.*', '', str(н))].add(str(r['ИНН']))
    for инн in по_номеру.values():
        инн = sorted(инн)
        for i in инн[1:]:
            слить(инн[0], i)
    по_сайту = collections.defaultdict(set)
    for r in комп:
        if хост(r.get('Сайт')):
            по_сайту[хост(r['Сайт'])].add(str(r['ИНН']))
    for инн in по_сайту.values():
        инн = sorted(инн)
        for i in инн[1:]:
            слить(инн[0], i)
    мобильных = collections.Counter(str(r['ИНН']) for r in конт if r.get('Мобильный'))
    сегменты = sorted({r.get('Сегмент') or '' for r in комп})

    def вектор(r):
        i = str(r['ИНН'])
        в = {'компаний': 1, 'с покупателем оборудования': int((r.get('Из них покупатели оборудования') or 0) > 0),
             'с ЛПР КЦ': int((r.get('Из них ЛПР КЦ') or 0) > 0), 'с номером': int((r.get('Номеров') or 0) > 0),
             'мобильных': мобильных[i], 'выручка, млрд': (float(r.get('Выручка, руб') or 0)) / 1e9,
             'есть в Битрикс': int(bool(r.get('Есть контакт в Битрикс')))}
        for с in сегменты:
            в['сегмент: ' + с] = int((r.get('Сегмент') or '') == с)
        return в
    кластеры = collections.defaultdict(list)
    for r in комп:
        кластеры[корень(str(r['ИНН']))].append(r)
    вес = {'компаний': 3, 'с покупателем оборудования': 4, 'с ЛПР КЦ': 3, 'с номером': 3, 'мобильных': 0.5,
           'выручка, млрд': 0.3, 'есть в Битрикс': 1}
    итог = [collections.Counter(), collections.Counter()]
    часть = {}

    def ценность(кл):
        return (max(вектор(r)['с покупателем оборудования'] for r in кл), max(вектор(r)['с ЛПР КЦ'] for r in кл),
                max(вектор(r)['с номером'] for r in кл), sum(вектор(r)['выручка, млрд'] for r in кл))
    for кл in sorted(кластеры.values(), key=ценность, reverse=True):
        сумма = collections.Counter()
        for r in кл:
            сумма.update(вектор(r))

        def перекос(k):
            а, б = итог[0].copy(), итог[1].copy()
            (а if k == 0 else б).update(сумма)
            return sum(вес.get(m, 1) * abs(а[m] - б[m]) for m in set(а) | set(б))
        k = min((0, 1), key=lambda k: (перекос(k), итог[k]['компаний']))
        итог[k].update(сумма)
        for r in кл:
            часть[str(r['ИНН'])] = k
    # доводка обменами: пары кластеров между частями, если обмен уменьшает общий перекос (мелкие сегменты)
    суммы = {}
    for ключ, кл in кластеры.items():
        с_ = collections.Counter()
        for r in кл:
            с_.update(вектор(r))
        суммы[ключ] = с_
    где = {ключ: часть[str(кл[0]['ИНН'])] for ключ, кл in кластеры.items()}

    def счёт(а, б):
        return sum((10 if m.startswith('сегмент') else вес.get(m, 1)) * abs(а[m] - б[m]) for m in set(а) | set(б))
    for _ in range(400):
        лучше = False
        а_кл = [x for x in суммы if где[x] == 0]
        б_кл = [x for x in суммы if где[x] == 1]
        база = счёт(итог[0], итог[1])
        for x in а_кл:
            for y in б_кл:
                if суммы[x]['компаний'] != суммы[y]['компаний']:
                    continue
                а = итог[0] - суммы[x] + суммы[y]
                б = итог[1] - суммы[y] + суммы[x]
                for m in set(итог[0]) | set(итог[1]):  # Counter вычитание отбрасывает нули — вернуть ключи
                    а.setdefault(m, 0)
                    б.setdefault(m, 0)
                if счёт(а, б) < база - 1e-9:
                    итог[0], итог[1] = а, б
                    где[x], где[y] = 1, 0
                    база = счёт(а, б)
                    лучше = True
                    break
            if лучше:
                break
        if not лучше:
            break
    for ключ, кл in кластеры.items():
        for r in кл:
            часть[str(r['ИНН'])] = где[ключ]
    # запись: копия книги без чужих строк (формат, ширины, фильтры сохраняются)
    for k, п in ((0, п1), (1, п2)):
        wb = load_workbook(п_in)
        for ws in wb.worksheets:
            шапка = [c.value for c in ws[1]]
            if 'ИНН' not in шапка:
                continue
            ки = шапка.index('ИНН') + 1
            удалить = [r for r in range(2, ws.max_row + 1) if часть.get(str(ws.cell(row=r, column=ки).value)) != k]
            # подряд идущие строки — одним вызовом (быстрее)
            for r in reversed(удалить):
                ws.delete_rows(r)
            if ws.auto_filter.ref:
                ws.auto_filter.ref = 'A1:%s%d' % (ws.cell(row=1, column=ws.max_column).column_letter, max(ws.max_row, 2))
        св = wb.create_sheet('Раздел', 0)
        св.append(['Показатель', 'Часть 1', 'Часть 2'])
        for m in list(вес) + ['сегмент: ' + с for с in сегменты]:
            св.append([m, round(итог[0][m], 1), round(итог[1][m], 1)])
        св.append([])
        св.append(['Компании одного холдинга (общий номер или сайт) — в одной части; делёж по ценности контактов, '
                   'выручке, сегментам и Битриксу.'])
        св.column_dimensions['A'].width = 40
        wb.save(п)
    print(json.dumps({'кластеров': len(кластеры), 'многокомпанийных': sum(1 for кл in кластеры.values() if len(кл) > 1),
                      'часть1': dict(итог[0]), 'часть2': dict(итог[1])}, ensure_ascii=False, indent=1, default=float))


if __name__ == '__main__':
    main(*sys.argv[1:4])
