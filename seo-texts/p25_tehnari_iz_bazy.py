# -*- coding: utf-8 -*-
"""Технари с личным мобильным, УЖЕ ЛЕЖАЩИЕ В БАЗЕ и невидимые из-за lower().

ПРЯМОЕ СЛЕДСТВИЕ ПЕРЕСЧЁТА. `sqlite3.lower()` не понижает кириллицу, и все прежние
отборы ролей через SQL молча теряли людей с большой буквы:

    person.position   «директор»    SQL   64  ->  Python  467   в 7,3 раза
    person.position   «начальник»   SQL   16  ->  Python   72   в 4,5 раза
    company.direktor  «директор»    SQL    7  ->  Python 1 190   в 170 раз

Ошибка не даёт ни исключения, ни предупреждения: число выглядит ответом. Значит
технические ЛПР могли лежать в базе всё это время, просто ни один запрос их не видел.

Прибор ищет их ЗАНОВО, средствами Python, и проверяет три условия ТЗ по одной записи:
должность техническая, номер личный мобильный, у контакта есть источник. Ничего не
пишет в базу — выкладывает файлом, чтобы это можно было проверить глазами прежде, чем
считать закрытием.
"""
import collections
import csv
import io
import json
import os
import re
import sqlite3
import urllib.request

BAZA = 'file:C:/seostat/data/p25.db?mode=ro'
VYHOD = r'C:\sender\_ops\P25-TEHNARI-IZ-BAZY-3S.csv'

KRUG12 = re.compile(
    r'главн\w+\s+(?:инженер|механик|энергетик|технолог|сварщик|метролог|конструктор)|'
    r'техническ\w+\s+директор|начальник\w*\s+(?:цеха|производств|участка|службы|'
    r'ремонт\w*|энерго\w*|отдела\s+главного)|\bмеханик|\bэнергетик|\bтехнолог|'
    r'\bинженер|КИПиА|АСУ', re.I)
NE_NASH = re.compile(r'персонал|кадр|закупк|снабж|бухгалт|юрист|секретар|маркетинг|'
                     r'продаж|устойчив\w+\s+развити|реклам|пресс|охран\w+\s+труда', re.I)


def lichnyy(n):
    c = re.sub(r'\D', '', str(n or ''))
    if len(c) == 11 and c[0] in '78':
        c = '7' + c[1:]
    return len(c) == 11 and c.startswith('79')


b = sqlite3.connect(BAZA, uri=True)
nashi = {i: n for i, n in b.execute('select inn, coalesce(predpriyatie,"") from company')}
mesta = {i: m for i, m in b.execute('select inn, coalesce(mesto_po_summe,9999) from company')}


def kolonki(t):
    return [r[1] for r in b.execute('pragma table_info(%s)' % t)]


sch = collections.Counter()
stroki = []
# Таблицы читаю по ФАКТИЧЕСКИМ колонкам, а не по памяти о схеме.
for tabl in ('contact', 'person'):
    try:
        polya = kolonki(tabl)
    except Exception:  # noqa: BLE001
        continue
    k_inn = next((x for x in polya if x.lower() in ('inn', 'company_inn')), '')
    k_fio = next((x for x in polya if x.lower() in ('fio', 'name', 'chelovek', 'imya')), '')
    k_pos = next((x for x in polya if 'position' in x.lower() or 'dolzh' in x.lower()), '')
    k_tel = [x for x in polya if re.search(r'tel|phone|nomer|value|znach|contact', x, re.I)]
    k_ist = [x for x in polya if re.search(r'source|ssylk|url|chem_podtver|quote|cit', x, re.I)]
    if not (k_pos and k_tel):
        sch['таблица %s: нет колонки должности или телефона' % tabl] += 1
        continue
    for r in b.execute('select %s from %s' % (','.join(polya), tabl)):
        z = dict(zip(polya, r))
        pos = str(z.get(k_pos) or '')
        if not KRUG12.search(pos) or NE_NASH.search(pos):
            continue
        nomer = next((str(z[x]) for x in k_tel if lichnyy(z.get(x))), '')
        if not nomer:
            sch['технарь в базе есть, личного мобильного нет'] += 1
            continue
        inn = str(z.get(k_inn) or '').strip()
        if inn not in nashi:
            sch['технарь с мобильным, но предприятие не наше'] += 1
            continue
        ist = ' | '.join(str(z.get(x)) for x in k_ist if z.get(x))[:400]
        sch['ТЕХНАРЬ С ЛИЧНЫМ МОБИЛЬНЫМ В БАЗЕ'] += 1
        if not ist:
            sch['  из них БЕЗ первоисточника — в меру не идёт'] += 1
        stroki.append({
            'mesto_po_summe': mesta.get(inn, 9999), 'inn': inn,
            'predpriyatie': nashi.get(inn, ''),
            'chelovek': str(z.get(k_fio) or ''), 'dolzhnost': pos[:90],
            'LICHNYY_MOBILNYY': nomer, 'tablica': tabl,
            'pervoistochnik': 'да' if ist else '',
            'chem_podtverzhdena': ist,
        })

# Один человек мог попасть из обеих таблиц — склеиваю по паре «человек + номер».
vidano, chistye = set(), []
for s in sorted(stroki, key=lambda x: x['mesto_po_summe']):
    k = (s['inn'], s['chelovek'].strip().lower(), re.sub(r'\D', '', s['LICHNYY_MOBILNYY']))
    if k in vidano:
        continue
    vidano.add(k)
    chistye.append(s)

otvet = ''
if chistye:
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=list(chistye[0].keys()), delimiter=';',
                       extrasaction='ignore')
    w.writeheader()
    w.writerows(chistye)
    open(VYHOD, 'w', encoding='utf-8-sig', newline='').write(buf.getvalue())
    url, tok = os.environ.get('DROP_URL', ''), os.environ.get('DROP_TOKEN', '')
    if url and tok:
        rq = urllib.request.Request(url.rstrip('/') + '/' + os.path.basename(VYHOD),
                                    data=buf.getvalue().encode('utf-8-sig'), method='PUT')
        rq.add_header('X-Drop-Token', tok)
        try:
            otvet = urllib.request.urlopen(rq, timeout=120).status
        except Exception as e:  # noqa: BLE001
            otvet = 'сбой: %s' % e

for s in chistye[:20]:
    print('  место %4s  %-28s %-26s %-18s %s' % (
        s['mesto_po_summe'], s['predpriyatie'][:28], s['chelovek'][:26],
        s['LICHNYY_MOBILNYY'], s['dolzhnost'][:30]))
for k, v in sch.most_common():
    print('REC %s\t%d' % (k, v))
print('ИТОГ ' + json.dumps({
    'человек': len(chistye), 'предприятий': len({s['inn'] for s in chistye}),
    'с первоисточником': len([s for s in chistye if s['pervoistochnik']]),
    'из первой сотни': len([s for s in chistye if s['mesto_po_summe'] <= 100]),
    'файл': os.path.basename(VYHOD) if chistye else '', 'дроп': otvet}, ensure_ascii=False))
