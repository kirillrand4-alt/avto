# -*- coding: utf-8 -*-
"""Сколько людей потерял узкий шаблон отчества. Замерить цену, а не просто починить.

НАХОДКА ЧУЖИМИ ГЛАЗАМИ. Враждебный проверяющий, читавший новый канал, заметил: шаблон
ФИО требовал `[А-ЯЁ][а-яё]{3,}` перед окончанием отчества, то есть трёх букв между
заглавной и «-ович». В «Юрьевич», «Юрьевна», «Львович», «Львовна» их ДВЕ. Проверено
прямым замером: из восьми живых написаний узкий шаблон теряет пять.

Потеря невидима: человек просто не находится, и запись выглядит пустой страницей, а не
ошибкой разбора. Ровно тот класс, что и пятизначные коды у телефонов, и `lower()` по
кириллице, и мёртвый заслон, — прибор молчит и молчание читается как ответ.

Прибор считает ЦЕНУ по уже собранному: сколько ФИО в сохранённых цитатах видит широкий
шаблон и не видит узкий. Это люди, за которых запросы УЖЕ заплачены, а имя не взято.
"""
import collections
import json
import os
import re

POTOKI = (r'C:\sender\_ops\p25-imena.jsonl', r'C:\sender\_ops\p25-obratnyy.jsonl',
          r'C:\sender\_ops\p25-dobit.jsonl', r'C:\sender\_ops\p25-dolzhnost.jsonl',
          r'C:\sender\_ops\p25-dobavochnyy.jsonl')
OKONCH = 'ович|евич|ьевич|инич|овна|евна|ьевна|ична'
UZKIY = re.compile(r'\b([А-ЯЁ][а-яё]{2,})\s+([А-ЯЁ][а-яё]{3,}(?:%s))\b' % OKONCH)
SHIROKIY = re.compile(r'\b([А-ЯЁ][а-яё]{2,})\s+([А-ЯЁ][а-яё]{2,}(?:%s))\b' % OKONCH)

sch = collections.Counter()
poteryannye = collections.Counter()
for put in POTOKI:
    if not os.path.exists(put):
        continue
    for ln in open(put, encoding='utf-8'):
        try:
            z = json.loads(ln)
        except Exception:  # noqa: BLE001
            continue
        # Все цитаты записи, где бы они ни лежали.
        citaty = []
        for spisok in ('lyudi', 'kontakty', 'naydeno'):
            # Поле с этим именем не везде список: в одном из потоков `naydeno` хранит
            # ЧИСЛО найденного. Перебирать его нельзя, и узнаётся это только проверкой
            # типа — имя поля совпадает, а смысл разный. Седьмой случай за смену, когда
            # одинаковое имя в разных потоках значит разное.
            znach = z.get(spisok)
            if not isinstance(znach, list):
                continue
            for n in znach:
                if isinstance(n, dict) and n.get('citata'):
                    citaty.append(n['citata'])
        for c in citaty:
            sch['цитат просмотрено'] += 1
            u = {m.group(0) for m in UZKIY.finditer(c)}
            sh = {m.group(0) for m in SHIROKIY.finditer(c)}
            for imya in sh - u:
                poteryannye[imya] += 1
                sch['ИМЁН ТЕРЯЛ УЗКИЙ ШАБЛОН'] += 1

print('какие отчества терялись чаще всего:')
otch = collections.Counter()
for imya, n in poteryannye.items():
    ch = imya.split()
    if len(ch) >= 2:
        otch[ch[-1]] += n
for o, n in otch.most_common(12):
    print('  %5d  %s' % (n, o))
print('\nпримеры потерянных имён:')
for imya, n in poteryannye.most_common(12):
    print('  %5d  %s' % (n, imya))
for k, v in sch.most_common():
    print('REC %s\t%d' % (k, v))
print('ИТОГ ' + json.dumps({
    'различных имён, невидимых узкому шаблону': len(poteryannye),
    'встреч всего': sum(poteryannye.values())}, ensure_ascii=False))
