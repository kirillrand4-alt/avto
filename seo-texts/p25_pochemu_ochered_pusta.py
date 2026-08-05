# -*- coding: utf-8 -*-
"""Почему очередь пуста при 45 новых именах: разошлись ли два счёта «уже спрошено».

Широкий сборщик сказал «45 новых имён, канал их не спрашивал». Прогон сказал «к обходу 0».
Оба не могут быть правы, и разница между ними — это либо честное «их и правда спрашивали»,
либо ДВА РАЗНЫХ КЛЮЧА одного и того же человека, то есть третий за смену случай, когда
два моих счёта считают по-разному и молча расходятся.

Прибор берёт эти самые 45 имён и по каждому отвечает: есть ли оно в потоке, каким
ключом сходится, и если не сходится — чем именно написание отличается.
"""
import collections
import csv
import json
import os
import re

SPLOSH = r'C:\sender\_ops\3s_p25_vhod_sploshnoy.csv'
VHOD = r'C:\sender\_ops\3s_p25_obratnyy_vhod.csv'
POTOKI = (r'C:\sender\_ops\p25-obratnyy.jsonl', r'C:\sender\_ops\p25-obratnyy-teh.jsonl')
csv.field_size_limit(10 ** 8)


def klyuch(f):
    return re.sub(r'\s+', ' ', str(f or '').strip()).lower()


def klyuch_yo(f):
    """Тот же ключ, но с «ё» сведённой к «е».

    ГИПОТЕЗА, КОТОРУЮ ПРОВЕРЯЕМ. Широкий сборщик считает 45 имён новыми, прогон говорит
    «к обходу 0», и оба читают одни и те же потоки. Значит расходятся не данные, а КЛЮЧИ.
    Самое дешёвое объяснение: «Фёдоров» и «Федоров» — одно имя, записанное в двух файлах
    по-разному, и мой ключ их различает, потому что понижает регистр и сжимает пробелы,
    а «ё» не трогает. Это тот же класс ошибки, что сравнение номеров по написанию.
    """
    return klyuch(f).replace('ё', 'е')


import json as _json
sprosheno = {}
for p in POTOKI:
    if not os.path.exists(p):
        continue
    for ln in open(p, encoding='utf-8'):
        try:
            z = _json.loads(ln)
        except Exception:  # noqa: BLE001
            continue
        f = z.get('fio') or z.get('chelovek') or ''
        if f:
            sprosheno[klyuch(f)] = (z.get('inn', ''), bool(z.get('err')))

novye = []
if os.path.exists(SPLOSH):
    for r in csv.DictReader(open(SPLOSH, encoding='utf-8-sig'), delimiter=';'):
        if r.get('fio'):
            novye.append((r.get('inn', ''), r['fio']))

v_vhode = set()
if os.path.exists(VHOD):
    for r in csv.DictReader(open(VHOD, encoding='utf-8-sig'), delimiter=';'):
        if r.get('fio'):
            v_vhode.add(klyuch(r['fio']))

sch = collections.Counter()
primery = []
for inn, fio in novye:
    k = klyuch(fio)
    est_v_potoke = k in sprosheno
    # Сходится ли имя, если свести «ё» к «е», когда точный ключ не сошёлся.
    if not est_v_potoke and klyuch_yo(fio) in {klyuch_yo(x) for x in sprosheno}:
        sch['сошлось ТОЛЬКО после сведения ё к е'] += 1
        est_v_potoke = True
    est_vo_vhode = k in v_vhode
    if est_v_potoke and est_vo_vhode:
        sch['честно: имя есть и в потоке, и во входе — спрошен'] += 1
    elif est_v_potoke:
        sch['спрошен, но во вход не попал'] += 1
    elif est_vo_vhode:
        sch['во входе есть, в потоке нет — ДОЛЖЕН БЫЛ СПРОСИТЬСЯ'] += 1
        if len(primery) < 8:
            primery.append(('во входе, не спрошен', inn, fio))
    else:
        sch['НИ во входе, НИ в потоке — потерян между сборщиками'] += 1
        if len(primery) < 8:
            primery.append(('потерян', inn, fio))

for vid, inn, fio in primery:
    print('  %-24s %-12s %s' % (vid, inn, fio))
for k, v in sch.most_common():
    print('REC %s\t%d' % (k, v))
print('ИТОГ ' + json.dumps({
    'новых по широкому сборщику': len(novye),
    'имён в потоке': len(sprosheno), 'имён во входе': len(v_vhode),
}, ensure_ascii=False))
