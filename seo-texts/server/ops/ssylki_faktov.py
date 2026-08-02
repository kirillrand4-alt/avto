# -*- coding: utf-8 -*-
"""Факты без ссылки на первоисточник: сколько, откуда, что восстановимо.

Пункт 8 задания владельца. Прежде чем «восстанавливать ссылки», надо понять,
чего именно не хватает: у части фактов ссылки нет, потому что источник её не
публикует (тогда восстанавливать нечего и надо честно это сказать), а у части
она ЕСТЬ, но лежит в соседнем поле или собирается по номеру документа.

Разные причины требуют разного, и объединять их в одну цифру «нет ссылки»
значит скрыть от себя, какая часть работы вообще выполнима.

Запуск: python ssylki_faktov.py
"""
import re
import sys
from collections import Counter

sys.path.insert(0, r'C:\seostat')
from app.services import centro_catalog, centro_medium  # noqa: E402

_URL = re.compile(r'https?://\S+', re.I)
# номер заключения ЭПБ: 30-ТУ-01213-2015, 01-ЗС-28410-2023
_ЭПБ = re.compile(r'\b(\d{2}[-–][А-ЯЁA-Z]{2,3}[-–]\d{4,6}[-–]\d{4})\b')
# номер закупки/процедуры: 32110511492, 2250860929
_ЗАКУПКА = re.compile(r'\b(3\d{10}|2\d{9})\b')


def main():
    with centro_catalog.connect() as conn:
        кол = centro_catalog.table_columns(conn, 'fact')
        print('колонки таблицы fact:', ', '.join(sorted(кол)))
        ряды = centro_catalog._rows(conn, 'SELECT * FROM fact', ())
    print(f'фактов всего: {len(ряды)}')

    без = 0
    по_источнику = Counter()
    восстановимо = Counter()
    примеры = {}
    for row in ряды:
        item = {
            **row,
            'status': row.get('status') or row.get('chto') or '',
            'model': row.get('model') or row.get('kto_ili_marka') or '',
            'equipment_type': (row.get('equipment_type')
                               or row.get('dolzhnost_ili_tip') or ''),
            'medium': row.get('medium') or row.get('rol') or '',
            'evidence': row.get('evidence') or row.get('chem_dokazano') or '',
            'quote': row.get('quote') or row.get('citata') or '',
        }
        if centro_medium.rejection_reason(item):
            continue          # мусор чинить незачем
        урл = (row.get('source_url') or row.get('ssylka') or '').strip()
        if урл.lower().startswith(('http://', 'https://')):
            continue
        без += 1
        ист = (row.get('source') or row.get('istochnik') or '').strip()
        по_источнику[ист or '(источник не назван)'] += 1

        # ЧТО можно восстановить: ищем в тексте признак, по которому ссылка
        # собирается однозначно
        поле = ' '.join(str(row.get(k) or '') for k in row)
        if _URL.search(поле):
            вид = 'ссылка ЕСТЬ в другом поле'
        elif _ЭПБ.search(поле):
            вид = 'номер заключения ЭПБ — ссылка собирается'
        elif _ЗАКУПКА.search(поле):
            вид = 'номер закупки — ссылка собирается'
        else:
            вид = 'зацепки нет'
        восстановимо[вид] += 1
        примеры.setdefault(вид, (ист, (item['evidence'] or item['quote'])[:150]))

    print(f'чистых фактов БЕЗ ссылки: {без}')
    print('\nпо источникам:')
    for и, n in по_источнику.most_common(12):
        print(f'  {n:>6}  {и[:60]}')
    print('\nчто из этого восстановимо:')
    for в, n in восстановимо.most_common():
        ист, обр = примеры[в]
        print(f'  {n:>6}  {в}')
        print(f'          пример [{ист[:30]}]: {обр}')


if __name__ == '__main__':
    main()
