# -*- coding: utf-8 -*-
r"""Тестовая партия: 100 наиболее разных компаний для проверки качества владельцем (09.10: «тестовая партия по всем
регионам рандомными запросами, вся цепочка, 100 наиболее разных компаний и их номеров/почт/сайтов/ЛПР»).

Берёт Excel тестового набора (pilot_xlsx.py) и выбирает 100 компаний по кругу «сегмент → регион»: сначала по одной на
каждый сегмент, затем следующий круг, внутри сегмента — регионы, которых ещё не было, обе страны. Контакты НЕ
фильтруются: в выборку идут и компании, где ничего не нашлось, — проверка должна показать честную картину.
Листы: «Сводка» (доли: сайт, номер, почта, ЛПР), «100 компаний», «Контакты 100», «Снято 100», «Не открылись (для Зенки)».

    python3 proba_100.py <MEYER-7t.xlsx> <PROBA-100.xlsx>
"""
import collections
import random
import sys

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill


def читать(wb, имя):
    if имя not in wb.sheetnames:
        return [], []
    стр = list(wb[имя].iter_rows(values_only=True))
    if not стр:
        return [], []
    шапка = [str(x or '') for x in стр[0]]
    return шапка, [dict(zip(шапка, r)) for r in стр[1:] if any(r)]


def инн(r):
    return str(r.get('ИНН / УНП') or r.get('ИНН') or '')


def выбрать(компании, n=100):
    rnd = random.Random(7)
    по_сегм = collections.defaultdict(list)
    for r in компании:
        по_сегм[str(r.get('Сегмент') or '')].append(r)
    for сп in по_сегм.values():
        rnd.shuffle(сп)
    выбор, регионы = [], collections.Counter()
    while len(выбор) < n and any(по_сегм.values()):
        for с in sorted(по_сегм, key=lambda x: -len(по_сегм[x])):
            if not по_сегм[с] or len(выбор) >= n:
                continue
            сп = по_сегм[с]
            # регион, которого в выборке меньше всего
            лучший = min(range(len(сп)), key=lambda j: регионы[сп[j].get('Регион')])
            r = сп.pop(лучший)
            регионы[r.get('Регион')] += 1
            выбор.append(r)
    return выбор


def лист(wb, имя, шапка, строки):
    ws = wb.create_sheet(имя)
    ws.append(шапка)
    for c in ws[1]:
        c.font = Font(bold=True, color='FFFFFF')
        c.fill = PatternFill('solid', fgColor='0B3D6E')
        c.alignment = Alignment(wrap_text=True, vertical='top')
    for r in строки:
        ws.append([r.get(h, '') if isinstance(r, dict) else r[i] for i, h in enumerate(шапка)])
    for i, h in enumerate(шапка, 1):
        ws.column_dimensions[ws.cell(1, i).column_letter].width = min(60, max(10, len(h) + 4))
    ws.freeze_panes = 'A2'


def main(п_in, п_out):
    wb_in = load_workbook(п_in, read_only=True)
    шк, компании = читать(wb_in, 'Компании')
    шс, контакты = читать(wb_in, 'Контакты')
    шсн, снято = читать(wb_in, 'Снято')
    шз, зенка = читать(wb_in, 'Не открылись (для Зенки)')
    выбор = выбрать(компании)
    ии = {инн(r) for r in выбор}
    к100 = [r for r in контакты if инн(r) in ии]
    по_инн = collections.defaultdict(list)
    for r in к100:
        по_инн[инн(r)].append(r)
    n = len(выбор) or 1

    def доля(усл):
        return '%d из %d (%d%%)' % (sum(1 for r in выбор if усл(r)), len(выбор), round(100 * sum(1 for r in выбор if усл(r)) / n))
    свод = [
        ['Компаний в партии (весь список теста)', len(компании)],
        ['Выбрано для проверки', len(выбор)],
        ['Сегментов', len({r.get('Сегмент') for r in выбор})],
        ['Регионов', len({r.get('Регион') for r in выбор})],
        ['Страны', ', '.join('%s %d' % kv for kv in collections.Counter(r.get('Страна') for r in выбор).items())],
        ['С сайтом', доля(lambda r: r.get('Сайт'))],
        ['С номером', доля(lambda r: any(c.get('Мобильный') or c.get('Рабочий') for c in по_инн[инн(r)]))],
        ['С почтой', доля(lambda r: any(c.get('E-mail') for c in по_инн[инн(r)]))],
        ['С контактом ЛПР «да»', доля(lambda r: any(c.get('ЛПР по оборудованию') == 'да' for c in по_инн[инн(r)]))],
        ['С ЛПР и ФИО', доля(lambda r: any(c.get('ЛПР по оборудованию') == 'да' and c.get('ФИО') for c in по_инн[инн(r)]))],
        ['Контактов всего', len(к100)],
        ['Что проверить', 'по ссылке-источнику: номер/почта стоит на странице; подпись (ФИО, должность) — у этого контакта; '
                          'сайт — этой компании; сегмент верный; ЛПР «да» — человек влияет на покупку оборудования'],
    ]
    wb = Workbook()
    wb.remove(wb.active)
    лист(wb, 'Сводка', ['Показатель', 'Значение'], свод)
    лист(wb, '100 компаний', шк, выбор)
    лист(wb, 'Контакты 100', шс or ['Название'], к100)
    if шсн:
        лист(wb, 'Снято 100', шсн, [r for r in снято if инн(r) in ии])
    if шз:
        лист(wb, 'Не открылись (для Зенки)', шз, [r for r in зенка if str(r.get('ИНН') or r.get('inn') or '') in ии])
    wb.save(п_out)
    for r in свод[:-1]:
        print('%s: %s' % tuple(r))


if __name__ == '__main__':
    main(*sys.argv[1:3])
