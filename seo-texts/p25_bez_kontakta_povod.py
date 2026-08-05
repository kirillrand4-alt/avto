# -*- coding: utf-8 -*-
"""381 предприятие P25 без единого контакта: у кого из них есть ИМЯ, а у кого ничего.

Аудит показал 381 предприятие из 491 без единого номера в выкладках, 66 из них в
первой сотне по продажам. Это не один вид простоя, а три, и лечатся они разным:

  А. ИМЯ ЕСТЬ, НОМЕРА НЕТ  -> работа обратного хода, он уже кормится ими;
  Б. ИМЕНИ НЕТ, ДОМЕН ЕСТЬ -> работа именного канала: домен известен, значит
                              подтверждённый человек стоит ~21 запрос, а не 250;
  В. НЕТ НИЧЕГО            -> сперва домен, и только потом имя.

Смысл прибора — не в счёте, а в РАЗДЕЛЕНИИ: пока эти 381 лежат одной кучей, каждый
канал берёт из неё вслепую и половину работы делает не тем инструментом. Раскладываю
по видам и по деньгам, чтобы каждый канал получил СВОЮ очередь.
"""
import collections
import csv
import glob
import io
import json
import os
import re
import sqlite3
import urllib.request

csv.field_size_limit(10 ** 8)
D = r'C:\seostat\drop\drop-storage'
OPS = r'C:\sender\_ops'
VYHOD = r'C:\sender\_ops\P25-BEZ-KONTAKTA-OCHERED-3S.csv'
SAYTY_FAJLY = ('3s_p25_sayty_ot_1s.csv', '3s_p25_sayty_2s.csv', '3s_p25_sayty_2s_002.csv',
               '3s_p25_sayty_iz_poiska.csv', '3s_p25_sayty_iz_potokov.csv',
               '3s_p25_sayty_iz_centro.csv', '3s_p25_sayty.csv')
KOL_TEL = ('telefon', 'znachenie', 'nomer', 'LICHNYY_MOBILNYY', 'telefony', 'mobilnyy')
KOL_FIO = ('fio', 'ФИО', 'chelovek', 'imya', 'fio_lpr')
KOL_INN = ('inn', 'ИНН')

b = sqlite3.connect('file:C:/seostat/data/p25.db?mode=ro', uri=True)
nashi = {i: n for i, n in b.execute('select inn, coalesce(predpriyatie,"") from company')}
mesta = {i: m for i, m in b.execute('select inn, coalesce(mesto_po_summe,9999) from company')}

# КОНТАКТ ЕСТЬ — только по ВЫКЛАДКАМ: что не выложено, того для владельца нет.
s_kontaktom = set()
for p in glob.glob(os.path.join(D, 'P25-*3S*.csv')):
    try:
        for r in csv.DictReader(open(p, encoding='utf-8-sig'), delimiter=';'):
            inn = (r.get('inn') or '').strip()
            if inn and any((r.get(k) or '').strip() for k in KOL_TEL):
                s_kontaktom.add(inn)
    except Exception:  # noqa: BLE001
        continue

# ИМЯ ИЗВЕСТНО — по ЛЮБОМУ файлу: имя это ещё не контакт, но это вход для канала.
s_imenem = collections.Counter()
for papka in (D, OPS):
    for p in glob.glob(os.path.join(papka, '*.csv')):
        try:
            with open(p, encoding='utf-8-sig', newline='') as f:
                rd = csv.DictReader(f, delimiter=';')
                polya = rd.fieldnames or []
                ki = next((x for x in polya if x and x.strip() in KOL_INN), '')
                kf = next((x for x in polya if x and x.strip() in KOL_FIO), '')
                if not (ki and kf):
                    continue
                for r in rd:
                    inn, fio = (r.get(ki) or '').strip(), (r.get(kf) or '').strip()
                    if inn and fio:
                        s_imenem[inn] += 1
        except Exception:  # noqa: BLE001
            continue

sayty = {}
for imya in SAYTY_FAJLY:
    p = os.path.join(OPS, imya)
    if not os.path.exists(p):
        continue
    for r in csv.DictReader(open(p, encoding='utf-8-sig'), delimiter=';'):
        v = (r.get('ves') or '').strip()
        if v.isdigit() and int(v) < 2:
            continue
        if r.get('inn') and r.get('sayt'):
            sayty.setdefault(r['inn'], r['sayt'])

sch = collections.Counter()
stroki = []
for inn, nazv in nashi.items():
    if inn in s_kontaktom:
        continue
    est_imya, est_domen = s_imenem.get(inn, 0), inn in sayty
    if est_imya and est_domen:
        vid, kanal = 'А+Б: есть и имя, и домен', 'обратный ход по ФИО, потом номер на сайте'
    elif est_imya:
        vid, kanal = 'А: имя есть, домена нет', 'обратный ход по ФИО'
    elif est_domen:
        vid, kanal = 'Б: домен есть, имени нет', 'именной канал (домен известен — ~21 запрос)'
    else:
        vid, kanal = 'В: нет ни имени, ни домена', 'сперва домен, затем имя'
    sch[vid] += 1
    stroki.append({'mesto_po_summe': mesta.get(inn, 9999), 'inn': inn,
                   'predpriyatie': nazv, 'vid_prostoya': vid, 'kakim_kanalom': kanal,
                   'imen_izvestno': est_imya, 'sayt': sayty.get(inn, '')})

stroki.sort(key=lambda s: s['mesto_po_summe'])
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

print('первая сотня по продажам, без единого контакта:')
for s in [x for x in stroki if x['mesto_po_summe'] <= 100][:18]:
    print('  место %4s  %-34s %-26s имён %d  %s' % (
        s['mesto_po_summe'], s['predpriyatie'][:34], s['vid_prostoya'][:26],
        s['imen_izvestno'], s['sayt'][:26]))
for k, v in sch.most_common():
    print('REC %s\t%d' % (k, v))
print('ИТОГ ' + json.dumps({
    'предприятий без контакта': len(stroki),
    'из первой сотни': len([s for s in stroki if s['mesto_po_summe'] <= 100]),
    'файл': os.path.basename(VYHOD), 'дроп': otvet}, ensure_ascii=False))
