# -*- coding: utf-8 -*-
"""Четыре файла базы Meyer без повторов компаний (владелец 07.10).

«Сделай каждый файл уникальным + я удалил из последнего часть строк компаний, их тоже удали».
  * Удалённые владельцем компании (есть в нашей версии CC, нет в его правке на листе «Компании»)
    убираются из ВСЕХ файлов и со всех листов.
  * Каждая компания — ровно в одном файле. Приоритет: 1 (ЛПР, мобильные и добавочные) →
    2 (ЛПР, остальные телефоны) → 4 (сайты CC, правка владельца) → 3 (номера без ролей).
  * Чистка на всех листах, где есть колонка «ИНН»; в «Сводку» сверху — блок о чистке.

    python unikalnye_4_fayla.py <папка с файлами> <папка для итога>
"""
import os
import sys
import time

from openpyxl import Workbook, load_workbook
from openpyxl.cell import WriteOnlyCell
from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE
from openpyxl.styles import Alignment, Font, PatternFill

ФАЙЛЫ = [  # (метка, исходник, итог)
    ('1', 'meyer-lpr-tel-0510.xlsx', '1-meyer-LPR-mobilnye-i-dobavochnye-0710.xlsx'),
    ('2', 'meyer-lpr-ost-0610.xlsx', '2-meyer-LPR-ostalnye-telefony-0710.xlsx'),
    ('4', 'cc_owner/cc-owner.xlsx', '4-CC-sayty-kompaniy-0710.xlsx'),
    ('3', 'meyer-nomera-stranicy-0610.xlsx', '3-meyer-nomera-bez-roley-0710.xlsx'),
]
ИМЯ_ФАЙЛА = {'1': 'файл 1 (ЛПР, мобильные/добавочные)', '2': 'файл 2 (ЛПР, остальные телефоны)',
             '4': 'файл 4 (сайты CC)', '3': 'файл 3 (номера без ролей)'}


def инн_листа(ws):
    rows = ws.iter_rows(values_only=True)
    h = next(rows, None) or ()
    if 'ИНН' not in h:
        return None
    i = h.index('ИНН')
    return {str(r[i]) for r in rows if r and r[i] not in (None, '')}


def пересобрать(src, dst, убрать, причины, приоритет_прочих=None):
    """Скопировать книгу без строк, чей ИНН в «убрать». Вернёт {лист: (было, стало)} и ИНН «Компаний»."""
    wb = load_workbook(src)
    out = Workbook(write_only=True)
    счёт, компании = {}, set()
    for ws in wb.worksheets:
        ширины = {k: d.width for k, d in ws.column_dimensions.items() if d.width}
        rows = list(ws.iter_rows(values_only=True))
        if not rows:
            out.create_sheet(ws.title)
            continue
        h = rows[0]
        i = h.index('ИНН') if 'ИНН' in h else None
        if ws.title == 'Сводка':
            continue  # пишется в конце, с блоком о чистке
        новый = out.create_sheet(ws.title)
        for k, w in ширины.items():
            новый.column_dimensions[k].width = w
        новый.freeze_panes = ws.freeze_panes
        шапка = []
        for v in h:
            c = WriteOnlyCell(новый, value=v)
            c.font = Font(bold=True, color='FFFFFF')
            c.fill = PatternFill('solid', fgColor='305496')
            c.alignment = Alignment(wrap_text=True, vertical='top')
            шапка.append(c)
        новый.append(шапка)
        n = 0
        for r in rows[1:]:
            if i is not None and r[i] not in (None, '') and str(r[i]) in убрать:
                continue
            новый.append([ILLEGAL_CHARACTERS_RE.sub('', v) if isinstance(v, str) else v for v in r])
            n += 1
            if ws.title == 'Компании' and i is not None and r[i]:
                компании.add(str(r[i]))
        if n and h:
            последняя = len(h)
            буква = ''
            while последняя:
                последняя, ост = divmod(последняя - 1, 26)
                буква = chr(65 + ост) + буква
            новый.auto_filter.ref = 'A1:%s%d' % (буква, n + 1)
        счёт[ws.title] = (len(rows) - 1, n)
    # «Сводка» первой: блок о чистке + исходная сводка
    св = out.create_sheet('Сводка', 0)
    св.column_dimensions['A'].width = 90
    св.column_dimensions['B'].width = 14
    b = Font(bold=True)

    def ж(т):
        c = WriteOnlyCell(св, value=т)
        c.font = b
        return c
    св.append([ж('Чистка %s: файл без повторов с другими файлами и без компаний, удалённых владельцем'
                % time.strftime('%d.%m.%Y'))])
    for т, n in причины:
        св.append(['  убрано компаний: ' + т, n])
    for лист, (было, стало) in счёт.items():
        св.append(['  лист «%s»: строк было %d, стало %d' % (лист, было, стало)])
    св.append(['  (числа в исходной сводке ниже — до чистки)'])
    св.append([])
    if 'Сводка' in wb.sheetnames:
        for r in wb['Сводка'].iter_rows(values_only=True):
            св.append([ILLEGAL_CHARACTERS_RE.sub('', v) if isinstance(v, str) else v for v in r])
    out.save(dst)
    return счёт, компании


def запреты(п):
    """Все запреты панели по ИНН (sender.db suppression scope=inn): сделки, конкуренты, не профиль."""
    import json
    out = {}
    for x in json.load(open(п, encoding='utf-8')):
        if x.get('scope') != 'inn':
            continue
        r, src = x.get('reason') or '', x.get('source') or ''
        if r == 'deal_in_progress' or 'сделка' in src.lower():
            out[x['value']] = 'идёт сделка (панель)'
        elif 'competitor' in r or 'конкурент' in r:
            out[x['value']] = 'конкурент (панель)'
        else:
            out[x['value']] = '%s (панель)' % r
    return out


def main(папка, итог, п_запреты):
    os.makedirs(итог, exist_ok=True)
    зап = запреты(п_запреты)
    # удалённые владельцем: есть в нашей версии CC, нет в его правке
    наш = инн_листа(load_workbook(os.path.join(папка, 'baza-cc-meyer-0710.xlsx'), read_only=True)['Компании'])
    его = инн_листа(load_workbook(os.path.join(папка, 'cc_owner/cc-owner.xlsx'), read_only=True)['Компании'])
    удалены = наш - его
    исходные_комп = {м: инн_листа(load_workbook(os.path.join(папка, src), read_only=True)['Компании'])
                     for м, src, _ in ФАЙЛЫ}
    спорные4 = инн_листа(load_workbook(os.path.join(папка, 'cc_owner/cc-owner.xlsx'), read_only=True)['Спорные']) or set()
    занято = {}  # ИНН -> метка файла, где компания остаётся
    итоги = {}
    def причины_для(м, доп=()):
        причины = [('удалены владельцем в файле 4' + (' (их строки на остальных листах)' if м == '4' else ''),
                    len(удалены) if м == '4' else len(удалены & исходные_комп[м]))]
        for кат in sorted(set(зап.values())):
            n = len({i for i, к in зап.items() if к == кат} & исходные_комп[м])
            if n:
                причины.append((кат, n))
        return причины

    for м, src, dst in ФАЙЛЫ:
        убрать = set(удалены) | set(занято) | set(зап)
        причины = причины_для(м)
        for м2 in ('1', '2', '4', '3'):
            n = len({i for i, где in занято.items() if где == м2} & исходные_комп[м])
            if n:
                причины.append(('уже есть в «%s»' % ИМЯ_ФАЙЛА[м2], n))
        счёт, компании = пересобрать(os.path.join(папка, src), os.path.join(итог, dst), убрать, причины)
        for i in компании:
            занято.setdefault(i, м)
        итоги[м] = (dst, счёт, причины)
    # файл 4, лист «Спорные»: убрать и компании, что уже в основном списке файла 3
    к3 = инн_листа(load_workbook(os.path.join(итог, итоги['3'][0]), read_only=True)['Компании'])
    убрать4 = set(удалены) | set(зап) | {i for i, где in занято.items() if где in ('1', '2', '3')}
    причины4 = причины_для('4') + [('уже есть в «%s»' % ИМЯ_ФАЙЛА[м2], len({i for i, где in занято.items() if где == м2} & (исходные_комп['4'] | спорные4)))
                                   for м2 in ('1', '2', '3') if {i for i, где in занято.items() if где == м2} & (исходные_комп['4'] | спорные4)]
    счёт4, _ = пересобрать(os.path.join(папка, 'cc_owner/cc-owner.xlsx'), os.path.join(итог, итоги['4'][0]), убрать4, причины4)
    итоги['4'] = (итоги['4'][0], счёт4, причины4)
    # проверка: ни одной компании (лист «Компании») в двух файлах
    наборы = {м: инн_листа(load_workbook(os.path.join(итог, d), read_only=True)['Компании']) for м, (d, _, _) in итоги.items()}
    повторов = sum(len(наборы[a] & наборы[b]) for a in наборы for b in наборы if a < b)
    for м, (d, счёт, причины) in итоги.items():
        print(м, d, {k: v for k, v in счёт.items()}, причины)
    # «Спорные» файла 4 против основных списков 1–3
    сп = инн_листа(load_workbook(os.path.join(итог, итоги['4'][0]), read_only=True)['Спорные']) or set()
    повт_сп = len(сп & (наборы['1'] | наборы['2'] | наборы['3']))
    # остаток запретов панели во всех листах всех файлов
    ост = 0
    for м, (d, _, _) in итоги.items():
        wb = load_workbook(os.path.join(итог, d), read_only=True)
        for ws in wb.worksheets:
            и = инн_листа(ws)
            if и:
                ост += len(и & set(зап))
    print('удалены владельцем:', len(удалены), '| повторов компаний между файлами:', повторов,
          '| «Спорные» файла 4 в списках 1–3:', повт_сп, '| ИНН из запретов панели во всех листах:', ост)


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2], sys.argv[3])
