# -*- coding: utf-8 -*-
"""Вход классификации «Meyer / КЦ / не подходит» по изготовителям ФСА (20.10, владелец: «давай классификацию на Sol»).

Кто: список «Изготовители» FSA-MEYER-VSE (без отсеянных и ликвидированных); ИП убраны (владелец: «ИП без почты или
телефона — убирай»; в чистом проходе карточек у ИП своих контактов нет). По каждой — строка для модели: название,
ОКВЭД (основной + доп.), сегменты конвейера по ОКВЭД (Meyer — pilot_otbor.СЕГМ, КЦ — kc_cel.СЕГМ; подсказка, не
решение), выручка, продукция из деклараций, товарные знаки, паспорт и описание с сайта, где есть.

    python3 fsa_klass3_vhod.py <FSA-MEYER-VSE.xlsx> <out.json>
"""
import ast
import json
import os
import re
import sys

import openpyxl

import kc_cel

ЗДЕСЬ = os.path.dirname(os.path.abspath(__file__))


def сегменты_meyer():
    """СЕГМ и ИСКЛ из pilot_otbor.py без импорта (он тянет серверные модули)."""
    t = open(os.path.join(ЗДЕСЬ, 'pilot_otbor.py'), encoding='utf-8').read()
    м = re.search(r'^СЕГМ = (\[.*?^\])', t, re.S | re.M)
    и = re.search(r"^ИСКЛ = re\.compile\((r'.*?'\s*\n\s*r'.*?')\)", t, re.S | re.M)
    return ast.literal_eval(м.group(1)), re.compile(ast.literal_eval('(' + и.group(1) + ')'))


def по_префиксу(код, таблица):
    лучший, итог = '', ''
    for п, имя in таблица:
        if код.startswith(п) and len(п) > len(лучший):
            лучший, итог = п, имя
    return итог


def сегм(осн, все, таблица, искл):
    if not осн or искл.match(осн):
        return ''
    с = по_префиксу(осн, таблица)
    if с:
        return с
    for д in все:
        if д != осн and not искл.match(д):
            с = по_префиксу(д, таблица)
            if с:
                return с + ' (по доп. ОКВЭД)'
    return ''


def main(путь, выход):
    СМ, ИМ = сегменты_meyer()
    wb = openpyxl.load_workbook(путь, read_only=True)
    it = wb['Компании'].iter_rows(values_only=True)
    H = list(next(it))
    I = {k: i for i, k in enumerate(H)}
    г = lambda r, k: r[I[k]] or ''  # noqa: E731
    out = {}
    for r in it:
        инн = str(r[0])
        if len(инн) != 10:
            continue
        осн = г(r, 'ОКВЭД основной')
        доп = [x.strip() for x in г(r, 'ОКВЭД доп. (с карточки)').split(',') if x.strip()]
        выр = r[I['Выручка, руб']] or 0
        ч = ['%s' % г(r, 'Изготовитель')[:90],
             'ОКВЭД %s' % (осн or '—') + ('; доп. %s' % ', '.join(доп[:10]) if доп else ''),
             'выручка %s' % ('%.0f млн' % (выр / 1e6) if выр else 'неизвестна')]
        см, ск = сегм(осн, доп, СМ, ИМ), сегм(осн, доп, kc_cel.СЕГМ, kc_cel.ИСКЛ)
        if см or ск:
            ч.append('сегмент по ОКВЭД: Meyer — %s; КЦ — %s' % (см or 'нет', ск or 'нет'))
        ч.append('продукция по декларациям (%s шт.): %s' % (г(r, 'Деклараций (всего)'), г(r, 'Продукция (все позиции)')[:450]))
        if г(r, 'Товарные знаки'):
            ч.append('знаки: %s' % г(r, 'Товарные знаки')[:80])
        for k, имя in (('Паспорт: продукция', 'сайт: продукция'), ('Паспорт: оборудование и линии', 'сайт: линии'),
                       ('Конвейер: Описание (по сайту)', 'сайт: описание')):
            if г(r, k):
                ч.append('%s: %s' % (имя, str(г(r, k))[:200]))
        out[инн] = ' | '.join(ч)
    json.dump(out, open(выход, 'w', encoding='utf-8'), ensure_ascii=False)
    print(len(out))


if __name__ == '__main__':
    main(*sys.argv[1:3])
