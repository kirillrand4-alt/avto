# -*- coding: utf-8 -*-
"""Кто записал 316 городских номеров как «личные». Отвечать по данным, а не по памяти.

Вопрос владельца «это у кого ошибка» решается счётом, и счёт уже показал главное:
в выкладках на дропе таких ошибок НОЛЬ у всех трёх сессий, а в базе p25 их 316 при
136 верных — то есть в базе неверны СЕМЬ ИЗ ДЕСЯТИ меток «личный».

Значит метку ставил не тот, кто добыл номер: файл 2-й сессии с номером Квасова несёт
только `chelovek` и `telefon`, колонки вида в нём нет вовсе. Вид появился при заливке.

Прибор смотрит происхождение таких строк: таблицу источников контактов и любые колонки,
где записано, откуда строка взялась. Цель не найти виноватого, а найти МЕСТО, где вид
проставляется, — потому что чинить надо там, а не в выгрузке.
"""
import collections
import json
import re
import sqlite3

BAZA = 'file:C:/seostat/data/p25.db?mode=ro'


def cifry(n):
    c = re.sub(r'\D', '', str(n or ''))
    if len(c) == 11 and c[0] in '78':
        return '7' + c[1:]
    if len(c) == 10 and c[0] == '9':
        return '7' + c
    return ''


b = sqlite3.connect(BAZA, uri=True)
polya = [r[1] for r in b.execute('pragma table_info(contact)')]
print('колонки contact: %s' % ', '.join(polya))
try:
    ist_polya = [r[1] for r in b.execute('pragma table_info(contact_source)')]
    print('колонки contact_source: %s' % ', '.join(ist_polya))
except Exception as e:  # noqa: BLE001
    ist_polya = []
    print('contact_source: %s' % e)

# Строки с ошибочной меткой и всё, что о них известно.
sch_ist, sch_avtor = collections.Counter(), collections.Counter()
primery = []
for r in b.execute('select %s from contact' % ','.join(polya)):
    z = dict(zip(polya, r))
    vid = ' '.join(str(z.get(k) or '') for k in polya
                   if re.search(r'\btip\b|vid|kind|type|lichn|priznak', k, re.I))
    if not re.search(r'личн|мобильн|сотов', vid, re.I):
        continue
    if re.search(r'не\s+личн|общий', vid, re.I):
        continue
    c = cifry(z.get('value'))
    if not c or c.startswith('79'):
        continue
    # Откуда строка: любые колонки происхождения.
    otkuda = ' | '.join('%s=%s' % (k, str(z[k])[:40]) for k in polya
                        if z.get(k) and re.search(
                            r'source|istoch|otkuda|kanal|ssylk|url|chem|pochemu|kem|avtor',
                            k, re.I))
    # Точное отнесение: по ИМЕНИ ФАЙЛА-ИСТОЧНИКА, а не по всей строке происхождения.
    ist_fajl = str(z.get('source') or '')
    u = ist_fajl.upper()
    avtor = ('2-я сессия' if '2S' in u else
             '1-я сессия' if '1S' in u else
             '3-я сессия (моё)' if '3S' in u else
             'источник не назван' if not ist_fajl else 'прочее: ' + ist_fajl[:30])
    sch_avtor[avtor] += 1
    sch_ist[otkuda[:90] or 'происхождение в строке не записано'] += 1
    if len(primery) < 10:
        primery.append((c, str(z.get('name') or z.get('person_id') or '')[:24], vid[:28],
                        otkuda[:110]))

print('\nпримеры ошибочных строк:')
for c, kto, vid, otkuda in primery:
    print('  %-12s %-24s %-28s %s' % (c, kto, vid, otkuda or '—'))
print('\nпроисхождение ошибочных строк:')
for k, v in sch_ist.most_common(12):
    print('  %5d  %s' % (v, k))
print('\nПО АВТОРУ ФАЙЛА-ИСТОЧНИКА:')
for k, v in sch_avtor.most_common():
    print('  %5d  %s' % (v, k))
print('ИТОГ ' + json.dumps({'ошибочных строк': sum(sch_ist.values()),
                            'по авторам': dict(sch_avtor)}, ensure_ascii=False))
