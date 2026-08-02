# -*- coding: utf-8 -*-
"""Какие марки компрессоров реально стоят у компаний базы.

Владелец просит карточки характеристик «конкретно для этой компании». Прежде
чем писать расшифровщик обозначений, надо увидеть, ЧТО он будет расшифровывать:
расшифровщик, покрывающий выдуманные марки, выглядит работающим и молчит на
живых.

Запуск: python marki_zamer.py
"""
import re
import sys
from collections import Counter

sys.path.insert(0, r'C:\seostat')
from app.services import centro_catalog, centro_medium  # noqa: E402


def main():
    with centro_catalog.connect() as conn:
        ряды = centro_catalog._rows(conn, 'SELECT * FROM fact', ())
    марки = Counter()
    чистых = 0
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
            continue
        чистых += 1
        for кусок in re.split(r'[|;,]', item['model']):
            к = кусок.strip()
            if 2 <= len(к) <= 40:
                марки[к] += 1
    print(f'чистых фактов: {чистых}, разных марок: {len(марки)}')
    print('топ-60 марок:')
    for м, n in марки.most_common(60):
        print(f'  {n:>5}  {м}')

    # какие ОБОЗНАЧЕНИЯ преобладают — по ним и писать разбор
    шаблоны = Counter()
    for м, n in марки.items():
        ш = re.sub(r'\d+', 'N', м.upper())
        шаблоны[ш] += n
    print('\nтоп-25 шаблонов обозначений (цифры заменены на N):')
    for ш, n in шаблоны.most_common(25):
        print(f'  {n:>5}  {ш}')


if __name__ == '__main__':
    main()
