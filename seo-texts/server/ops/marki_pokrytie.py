# -*- coding: utf-8 -*-
"""Скольким компаниям разбор марок реально даст карточку характеристик.

Разбор прошёл контрольный список — значит он РАБОТАЕТ. Сколько компаний он
покроет, контрольный список не говорит: покрытие в три компании из трёхсот
выглядит в коде так же успешно, как покрытие в двести.
"""
import sys
from collections import Counter

sys.path.insert(0, r'C:\seostat')
from app.services import centro_catalog, centro_marki  # noqa: E402


def main():
    with centro_catalog.connect() as conn:
        инны = [r['inn'] for r in centro_catalog._rows(
            conn, 'SELECT DISTINCT inn FROM fact', ())]
    с_карточками = 0
    машин = Counter()
    примеры = []
    for и in инны:
        м = centro_marki.po_faktam(centro_catalog.facts(и))
        if м:
            с_карточками += 1
            for x in м:
                машин[x['tip']] += 1
            if len(примеры) < 6:
                примеры.append((и, m_str(м)))
    print(f'компаний с фактами: {len(инны)}')
    print(f'получат карточки характеристик: {с_карточками} '
          f'({round(100 * с_карточками / max(1, len(инны)))}%)')
    print('машин по типам:')
    for т, n in машин.most_common():
        print(f'  {n:>5}  {т}')
    print('\nпримеры:')
    for и, с in примеры:
        print(f'  {и}: {с}')


def m_str(м):
    return ' | '.join(f"{x['marka']} ({x['podacha']}, {x['davlenie']})"
                      for x in м[:4])


if __name__ == '__main__':
    main()
