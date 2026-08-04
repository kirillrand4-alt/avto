# -*- coding: utf-8 -*-
"""Спросить ИНН у 36 компаний площадки, чей ИНН неизвестен. Замкнуть связь.

РАЗМЕР РАБОТЫ ИЗМЕРЕН, И ОН МАЛ: в скачанном встречено 384 компании, у 348 ИНН уже
известен из лежащих рядом файлов, спросить надо 36. На этих 36 висит 865 закупок, и
среди них «ФосАгро-Череповец» (91), «Аммофос» (62), «Череповецкий Азот» (38),
«Уральская Сталь ( Металлоинвест)» (13) — имена, которые с большой вероятностью
окажутся нашими покупателями.

ПОЧЕМУ ЭТО РЕШАЕТ ЗАДАЧУ, КОТОРУЮ НЕ РЕШИЛИ НИ ИМЯ, НИ cid. Название в выдаче
торговое: company_id 7571 подписан «Балаковские Минудобрения», а ИНН на его странице
5103070023 — это АО «АПАТИТ», наш покупатель. Наш `cid` из выгрузки не совпал с
`company_id` строк ни у одного из трёх проверенных. ИНН сходится.

ЕСЛИ ИНН НЕ НАШЁЛСЯ — ПИШУ, ЧТО ИМЕННО ЛЕЖИТ НА СТРАНИЦЕ. У «Уральской Стали» мой
шаблон ИНН не сработал, и молча записать «ИНН нет» значило бы принять свойство
шаблона за свойство страницы. Поэтому при промахе сохраняется кусок текста вокруг
слова «ИНН» — по нему видно, шаблон отстал или ИНН правда не напечатан.
"""
import collections
import csv
import io
import json
import os
import re
import sqlite3
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor

D = r'C:\seostat\drop\drop-storage'
SPISKI = (os.path.join(D, 'tp-spisok.csv'), os.path.join(D, 'tp-kartochki-polnye.csv'))
SLOVARI = (os.path.join(D, 'tp-zakupki-po-vladelcam.csv'),
           os.path.join(D, 'tp-cid-inn.csv'), os.path.join(D, 'tp-inn.csv'))
VYHOD = r'C:\sender\_ops\P25-TP-CID-INN-3S.csv'
COMP_URL = 'https://www.tender.pro/api/company/%s/view'
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) '
      'Chrome/120.0 Safari/537.36')
INN_RE = re.compile(r'ИНН[^0-9]{0,20}(\d{10}|\d{12})')
INN_OKNO = re.compile(r'.{0,60}ИНН.{0,80}', re.S)
TEG = re.compile(r'<[^>]+>')
csv.field_size_limit(10 ** 8)


def vzyat(url, popytok=3):
    for p in range(popytok):
        try:
            rq = urllib.request.Request(url, headers={'User-Agent': UA,
                                                      'Accept-Language': 'ru,en;q=0.8'})
            with urllib.request.urlopen(rq, timeout=60) as r:
                return r.read().decode('utf-8', 'replace')
        except Exception as e:  # noqa: BLE001
            if p == popytok - 1:
                return '__ОШИБКА__ %s' % type(e).__name__
            time.sleep(1.5 * (p + 1))


vstrecheno, zakupok = {}, collections.Counter()
for p in SPISKI:
    if not os.path.exists(p):
        continue
    with open(p, encoding='utf-8-sig', newline='') as f:
        for r in csv.DictReader(f, delimiter=';'):
            cid = str(r.get('company_id') or '').strip()
            if cid:
                vstrecheno.setdefault(cid, (r.get('company') or '').strip())
                zakupok[cid] += 1

izvestno = {}
for p in SLOVARI:
    if not os.path.exists(p):
        continue
    with open(p, encoding='utf-8-sig', newline='') as f:
        rd = csv.DictReader(f, delimiter=';')
        polya = rd.fieldnames or []
        kc = next((x for x in polya if x and x.lower() in ('company_id', 'cid')), '')
        ki = next((x for x in polya if x and x.lower() == 'inn'), '')
        if kc and ki:
            for r in rd:
                c, i = str(r.get(kc) or '').strip(), (r.get(ki) or '').strip()
                if c and i:
                    izvestno.setdefault(c, i)

b = sqlite3.connect('file:C:/seostat/data/p25.db?mode=ro', uri=True)
nashi = {i: n for i, n in b.execute('select inn, coalesce(predpriyatie,"") from company')}
mesta = {i: m for i, m in b.execute('select inn, coalesce(mesto_po_summe,9999) from company')}

zad = sorted((c for c in vstrecheno if c not in izvestno), key=lambda c: -zakupok[c])
print('к опросу %d компаний' % len(zad))


def odna(cid):
    h = vzyat(COMP_URL % cid)
    if not h or h.startswith('__ОШИБКА__'):
        return {'company_id': cid, 'inn': '', 'prichina': 'страница не открылась',
                'okno': ''}
    m = INN_RE.search(h)
    if m:
        return {'company_id': cid, 'inn': m.group(1), 'prichina': '', 'okno': ''}
    o = INN_OKNO.search(h)
    return {'company_id': cid, 'inn': '',
            'prichina': 'ИНН на странице шаблоном не найден',
            'okno': re.sub(r'\s+', ' ', TEG.sub(' ', o.group(0)))[:160] if o
                    else 'слова ИНН на странице нет вовсе'}


with ThreadPoolExecutor(max_workers=4) as ex:
    rez = list(ex.map(odna, zad))

sch = collections.Counter()
stroki = []
for r in rez:
    cid = r['company_id']
    inn = r['inn']
    nash = inn in nashi if inn else False
    if inn:
        sch['ИНН добыт'] += 1
        if nash:
            sch['ИЗ НИХ НАШИ ПОКУПАТЕЛИ'] += 1
    else:
        sch[r['prichina']] += 1
    stroki.append({'company_id': cid, 'inn': inn,
                   'nazvanie_na_ploshchadke': vstrecheno.get(cid, ''),
                   'nash_pokupatel_p25': 'да' if nash else '',
                   'predpriyatie_po_bazе': nashi.get(inn, '') if inn else '',
                   'mesto_po_summe': mesta.get(inn, '') if nash else '',
                   'zakupok_v_skachannom': zakupok[cid],
                   'prichina_esli_net': r['prichina'], 'okno_teksta': r['okno']})

stroki.sort(key=lambda s: (s['nash_pokupatel_p25'] != 'да', -s['zakupok_v_skachannom']))
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

for s in stroki[:20]:
    print('  %-8s %-13s закупок %4d  %-34s %s' % (
        s['company_id'], s['inn'] or '—', s['zakupok_v_skachannom'],
        s['nazvanie_na_ploshchadke'][:34],
        ('НАШ, место %s' % s['mesto_po_summe']) if s['nash_pokupatel_p25']
        else s['prichina_esli_net']))
for k, v in sch.most_common():
    print('REC %s\t%d' % (k, v))
print('ИТОГ ' + json.dumps({'спрошено': len(zad), 'файл': os.path.basename(VYHOD),
                            'дроп': otvet}, ensure_ascii=False))
