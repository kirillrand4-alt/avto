# -*- coding: utf-8 -*-
"""Вход обратного хода СО ВСЕХ файлов, где есть ИНН и ФИО. Конец узкому списку целей.

ПОЧЕМУ ЭТО ГЛАВНАЯ ПОЧИНКА СМЕНЫ. Час назад я записала «обратный ход исчерпан, ждать
нечего». Аудит показал:

    обратный ход спросил имён                 1 126
    имён добыто и НЕ спрошено ни разу        73 342   в 156 файлах
    предприятий P25 без единого контакта        381   из них 66 в первой сотне

Канал не был исчерпан ни минуты. Исчерпан был мой СПИСОК ВХОДОВ: сборщик читал четыре
файла, заданных именами, из ста пятидесяти шести имеющихся. Я трижды за смену записала
правило «канал широкий, а список целей узкий, и широта пропадает зря» — про реестр
ЭПБ, про tender.pro, про людей с карточек — и трижды не применила его к самому важному
своему каналу.

ЧТО МЕНЯЕТСЯ. Вход собирается не по списку имён файлов, а ПОИСКОМ: любой CSV на дропе
и в рабочей папке, где есть колонка с ИНН и колонка с ФИО. Имена колонок берутся из
заголовков, а не угадываются, и список синонимов широкий, потому что файлы писали три
сессии в разное время.

ЧТО НЕ МЕНЯЕТСЯ. Отбор строгий, как был: только полное ФИО (без отчества имя в
кавычках ищется плохо и жжёт общий пул), только ИНН из наших 491, только те, кого
канал ещё не спрашивал, и только те, у кого личного мобильного ещё нет. Порядок —
по месту предприятия в продажах: дороже тот, кто больше покупал.

ПРОВЕНАНС. В колонке `otkuda` стоит имя файла-источника, а если человек назван
несколькими файлами — все они через « | » и их число. Источники накапливаются.
"""
import collections
import csv
import glob
import io
import json
import os
import re
import sqlite3

csv.field_size_limit(10 ** 8)
PAPKI = (r'C:\seostat\drop\drop-storage', r'C:\sender\_ops')
VYHOD = r'C:\sender\_ops\3s_p25_vhod_sploshnoy.csv'
POTOKI = (r'C:\sender\_ops\p25-obratnyy.jsonl', r'C:\sender\_ops\p25-obratnyy-teh.jsonl',
          r'C:\sender\_ops\lpr-obratnyy.jsonl')

FIO_POLNOE = re.compile(r'^[А-ЯЁ][а-яё]{2,}\s+[А-ЯЁ][а-яё]{2,}\s+'
                        r'[А-ЯЁ][а-яё]{2,}(?:ович|евич|ьевич|овна|евна|ьевна|ична)$')
KOL_INN = ('inn', 'ИНН', 'inn_predpriyatiya', 'inn_vladelca', 'inn_zakazchika')
KOL_FIO = ('fio', 'ФИО', 'chelovek', 'imya', 'avtor', 'familiya', 'fio_lpr')
KOL_DOLZH = ('dolzhnost', 'должность', 'dolzh', 'post', 'rol', 'dolzhnost_v_tekste')
KOL_TEL = ('telefon', 'телефон', 'telefony', 'mobilnyy', 'nomer', 'znachenie',
           'LICHNYY_MOBILNYY')


def lichnyy(n):
    c = re.sub(r'\D', '', str(n or ''))
    if len(c) == 11 and c[0] in '78':
        c = '7' + c[1:]
    return len(c) == 11 and c.startswith('79')


def klyuch(fio):
    return re.sub(r'\s+', ' ', str(fio or '').strip()).lower()


sprosheno = set()
for p in POTOKI:
    if not os.path.exists(p):
        continue
    for ln in open(p, encoding='utf-8'):
        try:
            z = json.loads(ln)
        except Exception:  # noqa: BLE001
            continue
        f = klyuch(z.get('fio') or z.get('chelovek'))
        if f:
            sprosheno.add(f)

b = sqlite3.connect('file:C:/seostat/data/p25.db?mode=ro', uri=True)
nashi = {i: n for i, n in b.execute('select inn, coalesce(predpriyatie,"") from company')}
mesta = {i: m for i, m in b.execute('select inn, coalesce(mesto_po_summe,9999) from company')}

kand = {}
s_mobilnym = set()
sch = collections.Counter()
fajlov = 0
for papka in PAPKI:
    for p in sorted(glob.glob(os.path.join(papka, '*.csv'))):
        try:
            with open(p, encoding='utf-8-sig', newline='') as f:
                rd = csv.DictReader(f, delimiter=';')
                polya = rd.fieldnames or []
                ki = next((x for x in polya if x and x.strip() in KOL_INN), '')
                kf = next((x for x in polya if x and x.strip() in KOL_FIO), '')
                if not (ki and kf):
                    continue
                fajlov += 1
                kd = next((x for x in polya if x and x.strip() in KOL_DOLZH), '')
                kt = [x for x in polya if x and x.strip() in KOL_TEL]
                for r in rd:
                    inn = (r.get(ki) or '').strip()
                    fio = (r.get(kf) or '').strip()
                    if not (inn and fio):
                        continue
                    if any(lichnyy(r.get(x)) for x in kt):
                        s_mobilnym.add((inn, klyuch(fio)))
                    if inn not in nashi:
                        sch['не наш покупатель P25'] += 1
                        continue
                    if not FIO_POLNOE.match(fio):
                        sch['не полное ФИО — в кавычках ищется плохо'] += 1
                        continue
                    if klyuch(fio) in sprosheno:
                        sch['канал уже спрашивал'] += 1
                        continue
                    k = (inn, klyuch(fio))
                    z = kand.setdefault(k, {'inn': inn, 'fio': fio,
                                            'predpriyatie': nashi.get(inn, ''),
                                            'dolzhnost': '', 'ist': []})
                    if kd and (r.get(kd) or '').strip() and not z['dolzhnost']:
                        z['dolzhnost'] = (r.get(kd) or '').strip()[:80]
                    imya_f = os.path.basename(p)
                    if imya_f not in z['ist']:
                        z['ist'].append(imya_f)
        except Exception:  # noqa: BLE001
            continue

stroki = []
for k, z in kand.items():
    if k in s_mobilnym:
        sch['личный мобильный уже есть'] += 1
        continue
    sch['В ОБХОД'] += 1
    stroki.append({'inn': z['inn'], 'predpriyatie': z['predpriyatie'], 'fio': z['fio'],
                   'dolzhnost': z['dolzhnost'],
                   'otkuda': ' | '.join(z['ist'][:6]), 'istochnikov': len(z['ist']),
                   'mesto': mesta.get(z['inn'], 9999)})
stroki.sort(key=lambda s: (s['mesto'], -s['istochnikov']))

buf = io.StringIO()
w = csv.DictWriter(buf, fieldnames=['inn', 'predpriyatie', 'fio', 'dolzhnost', 'otkuda',
                                    'istochnikov'], delimiter=';', extrasaction='ignore')
w.writeheader()
w.writerows(stroki)
open(VYHOD, 'w', encoding='utf-8-sig', newline='').write(buf.getvalue())

for s in stroki[:12]:
    print('  место %4s  %-28s %-30s источников %d' % (
        s['mesto'], s['predpriyatie'][:28], s['fio'][:30], s['istochnikov']))
for k, v in sch.most_common():
    print('REC %s\t%d' % (k, v))
print('ИТОГ ' + json.dumps({
    'файлов с ИНН и ФИО прочитано': fajlov,
    'НОВЫХ ИМЁН ВО ВХОД': len(stroki),
    'предприятий': len({s['inn'] for s in stroki}),
    'из первой сотни по продажам': len([s for s in stroki if s['mesto'] <= 100]),
    'названы двумя и более источниками': len([s for s in stroki if s['istochnikov'] > 1]),
    'файл': os.path.basename(VYHOD)}, ensure_ascii=False))
