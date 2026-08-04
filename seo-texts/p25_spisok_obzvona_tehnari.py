# -*- coding: utf-8 -*-
"""Список обзвона: технари с ЛИЧНЫМ мобильным, по нашим деньгам. То, ради чего всё.

Мера владельца одна: сколько личных номеров ЛПР добавлено. Всё остальное —
промежуточное. В `P25-TP-KARTOCHKI-LYUDI-3S.csv` таких людей 92, но они лежат среди
2 900 строк вперемешку с почтами, городскими и людьми без контакта. Продавцу нужен
короткий список, отсортированный по деньгам, где каждая строка — это звонок.

ЧТО ЗДЕСЬ ЕСТЬ И ЧЕГО НЕТ. Есть: человек, его личный мобильный, должность из текста
карточки, чем доказана роль (дословная метка заказчика), ссылка на карточку, дата
закупки и предмет — чтобы продавец знал, с чего начать разговор. Нет: людей с общим
номером, людей без имени, строк, где метка спорит с должностью. Они не выброшены —
они в полном файле, просто звонить по ним нельзя.

ПОРЯДОК СТРОК. Сперва наши покупатели P25 по месту в продажах: они уже покупали, их
разговор начинается не с нуля. Потом остальные предприятия, у которых доказана
закупка компрессорного оборудования, — по свежести закупки.
"""
import collections
import csv
import io
import json
import os
import re
import sqlite3
import urllib.request

ISHODNIK = r'C:\sender\_ops\P25-TP-KARTOCHKI-LYUDI-3S.csv'
VYHOD = r'C:\sender\_ops\P25-OBZVON-TEHNARI-3S-001.csv'
csv.field_size_limit(10 ** 8)


def data_klyuch(s):
    """Дату сортируем как число, а не как строку: «09.2024» не больше «10.2023»."""
    m = re.search(r'(\d{2})\.(\d{2})\.(\d{4})', str(s or ''))
    return (m.group(3), m.group(2), m.group(1)) if m else ('0000', '00', '00')


b = sqlite3.connect('file:C:/seostat/data/p25.db?mode=ro', uri=True)
mesta = {i: m for i, m in b.execute('select inn, coalesce(mesto_po_summe,9999) from company')}
imena = {i: n for i, n in b.execute('select inn, coalesce(predpriyatie,"") from company')}
summy = {}
try:
    summy = {i: s for i, s in b.execute('select inn, coalesce(summa,0) from company')}
except Exception:  # noqa: BLE001
    pass

rows = list(csv.DictReader(open(ISHODNIK, encoding='utf-8-sig'), delimiter=';'))
sch = collections.Counter()
stroki = []
vidano = set()
for r in rows:
    if r.get('vid') != 'МОБИЛЬНЫЙ ЛИЧНЫЙ':
        continue
    if not r.get('chelovek'):
        sch['мобильный есть, человек не назван — звонить некому'] += 1
        continue
    if r.get('tehnicheskiy_krug') != 'да':
        sch['мобильный с именем, но круг не технический'] += 1
        continue
    inn = (r.get('inn') or '').strip()
    nomer = re.sub(r'\D', '', r.get('znachenie') or '')
    k = (inn, r['chelovek'].lower(), nomer)
    if k in vidano:
        continue
    vidano.add(k)
    nash = r.get('nash_pokupatel_p25') == 'да'
    sch['В СПИСОК ОБЗВОНА'] += 1
    if nash:
        sch['  из них наши покупатели P25'] += 1
    stroki.append({
        'nash_pokupatel': 'ДА' if nash else '',
        'mesto_po_summe': mesta.get(inn, '') if nash else '',
        'inn': inn,
        'predpriyatie': imena.get(inn) or r.get('predpriyatie', ''),
        'chelovek': r['chelovek'],
        'LICHNYY_MOBILNYY': r.get('znachenie', ''),
        'dolzhnost': r.get('dolzhnost_v_tekste', ''),
        'chem_dokazana_rol': 'заказчик написал «%s»' % (r.get('slova_roli') or ''),
        'data_zakupki': r.get('data_kartochki', ''),
        'predmet_zakupki': (r.get('predmet') or '')[:140],
        'ssylka_na_kartochku': r.get('ssylka', ''),
        'imya_v_kartochke': r.get('chelovek_v_kartochke', ''),
        'osnovanie': (r.get('osnovanie') or '')[:300],
    })

stroki.sort(key=lambda s: (s['nash_pokupatel'] != 'ДА',
                           s['mesto_po_summe'] if s['mesto_po_summe'] else 9999,
                           tuple(-int(x) for x in data_klyuch(s['data_zakupki']))))

buf = io.StringIO()
w = csv.DictWriter(buf, fieldnames=list(stroki[0].keys()), delimiter=';',
                   extrasaction='ignore')
w.writeheader()
w.writerows(stroki)
open(VYHOD, 'w', encoding='utf-8-sig', newline='').write(buf.getvalue())

otvet = ''
url, tok = os.environ.get('DROP_URL', ''), os.environ.get('DROP_TOKEN', '')
if url and tok:
    rq = urllib.request.Request(url.rstrip('/') + '/' + os.path.basename(VYHOD),
                                data=buf.getvalue().encode('utf-8-sig'), method='PUT')
    rq.add_header('X-Drop-Token', tok)
    try:
        otvet = urllib.request.urlopen(rq, timeout=120).status
    except Exception as e:  # noqa: BLE001
        otvet = 'сбой: %s' % e

for s in stroki[:16]:
    print('  %-3s %-30s %-28s %-18s %s' % (
        s['mesto_po_summe'] or '—', s['predpriyatie'][:30], s['chelovek'][:28],
        s['LICHNYY_MOBILNYY'], (s['dolzhnost'] or '')[:22]))
for k, v in sch.most_common():
    print('REC %s\t%d' % (k, v))
print('ИТОГ ' + json.dumps({
    'строк в списке': len(stroki),
    'наших покупателей P25': len({s['inn'] for s in stroki if s['nash_pokupatel']}),
    'всего предприятий': len({s['inn'] for s in stroki if s['inn']}),
    'файл': os.path.basename(VYHOD), 'дроп': otvet}, ensure_ascii=False))
