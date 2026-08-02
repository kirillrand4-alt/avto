# -*- coding: utf-8 -*-
"""Колонки BEZ-TEHLPR-1486.csv и сколько там имён — прежде чем искать сайты.

755 целей вообще не имеют строки в `companies`, значит имя для запроса в
выдачу может быть только в этом файле. Если его там нет, поиск сайта по ним
невозможен, и это надо знать до прогона, а не после нулевого выхода.
"""
import csv
import io
import json
import os

ДРОП = r'C:\seostat\drop\drop-storage'

csv.field_size_limit(10 ** 7)
п = os.path.join(ДРОП, 'BEZ-TEHLPR-1486.csv')
ряды = list(csv.DictReader(io.StringIO(
    open(п, encoding='utf-8-sig', errors='replace').read()), delimiter=';'))
поля = list(ряды[0].keys()) if ряды else []
заполнено = {к: sum(1 for r in ряды if (r.get(к) or '').strip()) for к in поля}
print(json.dumps({
    'строк': len(ряды), 'колонки': поля, 'заполнено': заполнено,
    'первая': {к: (ряды[0].get(к) or '')[:60] for к in поля} if ряды else {},
}, ensure_ascii=False))
