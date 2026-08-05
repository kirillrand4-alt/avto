# -*- coding: utf-8 -*-
"""Каким ключом панель скрывает ЧЕЛОВЕКА. Не «умеет ли», а что именно кладёт в value.

В `hidden_item` лежат три вида: fact 24 457, company 931, phone 1. Вида `person` в базе
нет ни одного — при этом в исходниках панели слово `person` среди видов встречается.
Значит либо она умеет скрывать человека и этим ни разу не пользовались, либо слово стоит
не про скрытие.

РАЗНИЦА РЕШАЮЩАЯ, и ошибиться здесь легко тихо. Если ключом человека служит его id, а я
запишу ИНН с фамилией, скрытие ляжет в таблицу и не совпадёт ни с чем: панель покажет
то же самое, а я отчитаюсь, что отдала чистые данные. Это ровно тот класс промаха, на
котором я сегодня уже обожглась девять раз, — угаданное имя поля даёт правдоподобный
ноль вместо ошибки.

Прибор печатает КАЖДУЮ строку исходников панели, где рядом стоят скрытие и человек:
чтение (откуда вычитается скрытое), запись (куда кладётся) и вид ключа. Ничего не пишет.
"""
import collections
import io
import json
import os
import re

KORNI = (r'C:\sender\server', r'C:\sender\web\src', r'C:\sender')
MOYO = re.compile(r'[\\/](?:_ops|_bak[^\\/]*|tests?)[\\/]|[\\/][123]s_|_[123]s\.py$', re.I)
RASSH = ('.py', '.js', '.jsx', '.ts', '.tsx', '.html')

# Что ищем: строки про hidden_item и всё, что стоит рядом со словом person/contact.
PRO_SKRYTIE = re.compile(r'hidden_item|hidden_leads|skryt|скрыт', re.I)
PRO_CHELOVEKA = re.compile(r"\bperson\b|wrong_contact|flag_contact|contact_id|person_id", re.I)

sch = collections.Counter()
stroki = []
vidy_ryadom = collections.Counter()
seen = set()
for koren in KORNI:
    for put, papki, fayly in os.walk(koren):
        if re.search(r'[\\/](?:node_modules|\.git|__pycache__|dist)[\\/]', put + os.sep):
            papki[:] = []
            continue
        for f in fayly:
            if not f.lower().endswith(RASSH):
                continue
            p = os.path.join(put, f)
            if MOYO.search(p) or p in seen:
                continue
            seen.add(p)
            try:
                if os.path.getsize(p) > 3 * 1024 * 1024:
                    continue
                t = io.open(p, encoding='utf-8', errors='replace').read()
            except Exception:  # noqa: BLE001
                continue
            if 'hidden_item' not in t and 'hidden_leads' not in t:
                continue
            sch['файлов панели со скрытием'] += 1
            ls = t.split('\n')
            for i, s in enumerate(ls):
                if not PRO_SKRYTIE.search(s):
                    continue
                # Окно вокруг строки: ключ часто виден на соседней.
                okno = '\n'.join(ls[max(0, i - 3):i + 4])
                if PRO_CHELOVEKA.search(okno):
                    stroki.append((p[-56:], i + 1, s.strip()[:150]))
                    sch['строк про скрытие ЧЕЛОВЕКА'] += 1
                for m in re.finditer(r"kind\s*(?:=|==|:|,)\s*['\"]([a-z_]+)['\"]", okno):
                    vidy_ryadom[m.group(1)] += 1

print('=== строки панели, где скрытие стоит рядом с человеком')
for p, n, s in stroki[:40]:
    print('  %s:%-5d %s' % (p, n, s))
if not stroki:
    print('  НИ ОДНОЙ — панель скрывать человека не умеет, нужен другой путь')

print('\n=== виды, встречающиеся рядом со скрытием')
for v, n in vidy_ryadom.most_common(16):
    print('    %-18s %d' % (v, n))

for k, v in sch.most_common():
    print('REC %s\t%d' % (k, v))
print('ИТОГ ' + json.dumps({'строк про скрытие человека': len(stroki),
                            'виды рядом со скрытием': sorted(vidy_ryadom)},
                           ensure_ascii=False))
