# -*- coding: utf-8 -*-
"""Исправитель A: только ЧТЕНИЕ. Междугородние коды из текста страниц-источников
(contact.fragment): «8 (3452) 68-27-50» -> код 3452 у номера 73452682750. Нужны для
читаемого показа номера «+7 (3452) 68-27-50». Номеров не выводит — только коды и счёт.
-> на дроп `fixA_kody.json`.

    python3 zapusk_na_servere.py fixA_kody.py
"""
import io
import json
import os
import re
import sqlite3

KAT = r'C:\centro2\data\meyer_baza1.db'
DROP = r'C:\seostat\drop\drop-storage'
k = sqlite3.connect('file:%s?mode=ro' % KAT, uri=True)
SKOBKI = re.compile(r'(?:\+?7|8)?[\s\-]*\(\s*(\d[\d\s\-]{1,6}\d)\s*\)\s*([\d][\d\s\-]{3,10}\d)')
kody = {}
vsego = s_kodom = 0
for value, frag in k.execute("select value, coalesce(fragment,'') from contact where kind='phone'"):
    d = re.sub(r'\D', '', re.sub(r'(доб|доп|вн)\.?.*$', '', str(value or ''), flags=re.I))
    if len(d) != 11:
        continue
    vsego += 1
    nac = d[1:]
    for m in SKOBKI.finditer(frag):
        kod = re.sub(r'\D', '', m.group(1))
        mest = re.sub(r'\D', '', m.group(2))
        if kod.startswith('8') and len(kod) >= 4 and kod[1:] + mest == nac:
            kod = kod[1:]
        if kod + mest == nac and 3 <= len(kod) <= 5:
            kody[kod] = kody.get(kod, 0) + 1
            s_kodom += 1
            break
# конфликт: один код — префикс другого (тогда таблица неоднозначна)
konflikt = sorted([a, b] for a in kody for b in kody if a != b and b.startswith(a))
io.open(os.path.join(DROP, 'fixA_kody.json'), 'w', encoding='utf-8').write(json.dumps(
    {'vsego_11': vsego, 's_kodom': s_kodom, 'kody': kody, 'konflikt': konflikt}, ensure_ascii=False, indent=0))
print('номеров 11 цифр: %d, код из страницы: %d, разных кодов: %d, конфликтов: %d' % (vsego, s_kodom, len(kody), len(konflikt)))
