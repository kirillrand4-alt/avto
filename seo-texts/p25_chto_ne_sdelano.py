# -*- coding: utf-8 -*-
"""Что лежит добытым и НИ РАЗУ не спрошено ни одним каналом. Аудит простоя.

Владелец спросил: всё ли, что умею, сделано. Отвечать надо не памятью, а счётом, и
считать надо ИМЕННО ПРОСТОЙ: сколько имён, предприятий и поводов добыто и лежит, не
дойдя ни до одного канала.

Час назад я написала «обратный ход исчерпан, ждать нечего». Проверяю это утверждение
против файлов, потому что у него есть очевидный контрпример: 3 916 фамилий из
патентов, которые в обратный ход не заводились ни разу.
"""
import collections
import csv
import glob
import json
import os
import re
import sqlite3

csv.field_size_limit(10 ** 8)
D = r'C:\seostat\drop\drop-storage'
OPS = r'C:\sender\_ops'

FIO_POLNOE = re.compile(r'^[А-ЯЁ][а-яё]{2,}\s+[А-ЯЁ][а-яё]{2,}\s+'
                        r'[А-ЯЁ][а-яё]{2,}(?:ович|евич|ьевич|овна|евна|ьевна|ична)$')

# Кого обратный ход УЖЕ спрашивал — по потоку, а не по входному файлу.
sprosheno = set()
for p in (os.path.join(OPS, 'p25-obratnyy.jsonl'), os.path.join(OPS, 'p25-obratnyy-teh.jsonl'),
          os.path.join(OPS, 'lpr-obratnyy.jsonl')):
    if not os.path.exists(p):
        continue
    for ln in open(p, encoding='utf-8'):
        try:
            z = json.loads(ln)
        except Exception:  # noqa: BLE001
            continue
        f = (z.get('fio') or z.get('chelovek') or '').strip().lower()
        if f:
            sprosheno.add(f)
print('обратный ход спрашивал имён: %d' % len(sprosheno))

# ИСТОЧНИКИ ИМЁН НА ДИСКЕ. Ищу широко: любой CSV, где есть колонка с ФИО.
KOL_FIO = ('fio', 'ФИО', 'chelovek', 'imya', 'avtor', 'familiya')
itog = {}
for p in sorted(set(glob.glob(os.path.join(D, '*.csv')) + glob.glob(os.path.join(OPS, '*.csv')))):
    try:
        with open(p, encoding='utf-8-sig', newline='') as f:
            rd = csv.DictReader(f, delimiter=';')
            polya = rd.fieldnames or []
            kf = next((x for x in polya if x and x.strip() in KOL_FIO), '')
            if not kf:
                continue
            vsego, polnyh, novyh = 0, 0, 0
            novye_primery = []
            for r in rd:
                v = (r.get(kf) or '').strip()
                if not v:
                    continue
                vsego += 1
                if not FIO_POLNOE.match(v):
                    continue
                polnyh += 1
                if v.lower() not in sprosheno:
                    novyh += 1
                    if len(novye_primery) < 2:
                        novye_primery.append(v)
    except Exception:  # noqa: BLE001
        continue
    if novyh:
        itog[os.path.basename(p)] = {'имён': vsego, 'полных ФИО': polnyh,
                                     'НЕ СПРОШЕНО': novyh, 'пример': novye_primery}

for k, v in sorted(itog.items(), key=lambda x: -x[1]['НЕ СПРОШЕНО'])[:20]:
    print('  %-46s %s' % (k[:46], json.dumps(v, ensure_ascii=False)))

# ВТОРОЙ ПРОСТОЙ: предприятия P25 без единого контакта в выкладках.
b = sqlite3.connect('file:C:/seostat/data/p25.db?mode=ro', uri=True)
nashi = {i: m for i, m in b.execute('select inn, coalesce(mesto_po_summe,9999) from company')}
s_kontaktom = set()
for p in glob.glob(os.path.join(D, 'P25-*3S*.csv')):
    try:
        for r in csv.DictReader(open(p, encoding='utf-8-sig'), delimiter=';'):
            inn = (r.get('inn') or '').strip()
            if inn and any((r.get(k) or '').strip()
                           for k in ('telefon', 'znachenie', 'nomer', 'LICHNYY_MOBILNYY')):
                s_kontaktom.add(inn)
    except Exception:  # noqa: BLE001
        continue
bez = sorted((i for i in nashi if i not in s_kontaktom), key=lambda i: nashi[i])

print('ИТОГ ' + json.dumps({
    'источников имён с непройденными': len(itog),
    'ИМЁН НЕ СПРОШЕНО ВСЕГО': sum(v['НЕ СПРОШЕНО'] for v in itog.values()),
    'предприятий P25 без единого контакта': len(bez),
    'из них в первой сотне по продажам': len([i for i in bez if nashi[i] <= 100]),
}, ensure_ascii=False))
