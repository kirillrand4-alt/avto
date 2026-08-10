# -*- coding: utf-8 -*-
"""Счёт не сходится: 62 взято + 138 снято = 200, а строк в потоке 179. Разбираю ЧЕМ меряли.

Правило, выученное сегодня и стоившее целого захода: если счётчик внутри прогона больше,
чем все различные значения в файле, — сломан счётчик, а не файл. Здесь ровно тот случай, и
я не двигаюсь дальше, пока не назову причину числом.

Меряю на сервере, по тем же файлам, что читал сборщик:

    строк в потоке контактных лиц
    из них: без ИНН | битый JSON | машина не доказана | номер короче десяти цифр
    из них: ключ (ИНН, номер) уже занят строкой с личным номером — такие сборщик
            пропускает МОЛЧА, и вот их-то в разнице и не хватает

Только чтение. Числа в КОНЦЕ.
"""
import collections
import io
import json
import os
import re

OPS = r'C:\sender\_ops'
KONT = os.path.join(OPS, 'PARK-EIS-KONTAKTNOE-LICO-3S.jsonl')
SVODKA = os.path.join(OPS, 'PARK-SVODKA-CHELOVEK-ROL-NOMER-3S.jsonl')
SPISOK = os.path.join(OPS, 'PARK-SPISOK-DLYA-ZVONKA-3S.csv')
PARK = ['park_ingest_3.jsonl', 'park_ingest_3b.jsonl', 'park_ingest_3c.jsonl']

mash = set()
for p in PARK:
    put = os.path.join(OPS, p)
    if not os.path.exists(put):
        continue
    for s in io.open(put, encoding='utf-8'):
        try:
            o = json.loads(s)
        except Exception:  # noqa: BLE001
            continue
        if o.get('inn'):
            mash.add(o['inn'])

# ключи, занятые строками с личным номером (первый класс списка)
zanyato = set()
if os.path.exists(SVODKA):
    for s in io.open(SVODKA, encoding='utf-8'):
        try:
            o = json.loads(s)
        except Exception:  # noqa: BLE001
            continue
        if o.get('ishod') != 'ПОЛНЫЙ':
            continue
        n = re.sub(r'\D', '', o.get('nomer') or '')
        if o.get('inn') and len(n) == 10:
            zanyato.add((o['inn'], n))

vsego, ish = 0, collections.Counter()
for s in io.open(KONT, encoding='utf-8'):
    if not s.strip():
        ish['пустая строка файла'] += 1
        continue
    vsego += 1
    try:
        o = json.loads(s)
    except Exception:  # noqa: BLE001
        ish['битый JSON'] += 1
        continue
    inn = o.get('inn') or ''
    nomer = re.sub(r'\D', '', o.get('telefon') or '')
    if not inn:
        ish['ИНН пуст'] += 1
        continue
    if inn not in mash:
        ish['машина у ИНН не доказана'] += 1
        continue
    if len(nomer) < 10:
        ish['номер короче десяти цифр'] += 1
        continue
    if (inn, nomer[-10:]) in zanyato:
        ish['ключ занят строкой с личным номером — сборщик молчит'] += 1
        continue
    ish['должно попасть в список'] += 1

v_spiske = 0
if os.path.exists(SPISOK):
    for s in io.open(SPISOK, encoding='utf-8-sig'):
        if 'контактное лицо закупки' in s:
            v_spiske += 1

print('\n\n########## ЧИСЛА')
print('  строк в потоке контактных лиц      %5d' % vsego)
for k, v in ish.most_common():
    print('     %-56s %5d' % (k[:56], v))
print('  строк «контактное лицо» в готовом списке %5d' % v_spiske)
print('  ИНН с машиной                      %5d' % len(mash))
print('  ключей занято личными номерами     %5d' % len(zanyato))
snyato = sum(v for k, v in ish.items() if k != 'должно попасть в список')
print('  проверка: снято %d + должно попасть %d = %d, строк %d %s'
      % (snyato, ish['должно попасть в список'], snyato + ish['должно попасть в список'],
         vsego, 'СХОДИТСЯ' if snyato + ish['должно попасть в список'] == vsego
         else 'НЕ СХОДИТСЯ'))
print('ИТОГ ' + json.dumps({'строк': vsego, 'должно попасть': ish['должно попасть в список'],
                            'в списке': v_spiske}, ensure_ascii=False))
