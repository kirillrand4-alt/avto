# -*- coding: utf-8 -*-
"""Какими словами мои каналы ЗАПИСЫВАЮТ пройденную приёмку. Прочитать, а не сочинить.

Мера упала с 30 до 6, и 56 строк отпали с пометкой «первоисточника в строке нет». Но
эти строки лежат в файлах ГОДНЫХ — то есть приёмку при выкладке они прошли. Значит
узок теперь мой список формул: я его СОЧИНИЛА по памяти, вместо того чтобы прочитать,
как приёмка пишется на самом деле.

Это ровно то же, что было с именами полей: шестой раз за смену я подставила своё
представление вместо того, что записано. Прибор печатает все различные формулировки с
их числом — по ним и надо строить признак.
"""
import collections
import csv
import glob
import json
import os
import re

D = r'C:\seostat\drop\drop-storage'
csv.field_size_limit(10 ** 8)
OTKAZ_V_IMENI = ('ne-podtverzhdeno', 'spornaya-privyazka', 'obshchie', 'bez-nomera',
                 'ne-nashi', 'otsev', 'karantin')
KOL_IST = ('pervoistochnik', 'chem_podtverzhdena', 'chem_dokazana_rol', 'pochemu',
           'pochemu_stranica')

godnye, otklonennye = collections.Counter(), collections.Counter()
for p in sorted(glob.glob(os.path.join(D, 'P25-*3S*.csv'))):
    otkaz = any(x in os.path.basename(p).lower() for x in OTKAZ_V_IMENI)
    try:
        rows = list(csv.DictReader(open(p, encoding='utf-8-sig'), delimiter=';'))
    except Exception:  # noqa: BLE001
        continue
    for r in rows:
        for k in KOL_IST:
            v = (r.get(k) or '').strip()
            if not v:
                continue
            # Формула без переменной части: имена доменов и предприятий убираю, чтобы
            # одинаковые по смыслу записи сливались в одну строку отчёта.
            f = re.sub(r'«[^»]*»', '«…»', v)
            f = re.sub(r'https?://\S+', '<ссылка>', f)[:90]
            (otklonennye if otkaz else godnye)[f] += 1

print('=== ФОРМУЛЫ В ФАЙЛАХ ГОДНЫХ (по ним и надо строить признак приёмки)')
for f, n in godnye.most_common(22):
    print('  %5d  %s' % (n, f))
print('\n=== ФОРМУЛЫ В ФАЙЛАХ ОТКЛОНЁННЫХ (эти должны отсекаться)')
for f, n in otklonennye.most_common(12):
    print('  %5d  %s' % (n, f))
print('ИТОГ ' + json.dumps({'различных формул у годных': len(godnye),
                            'различных формул у отклонённых': len(otklonennye)},
                           ensure_ascii=False))
