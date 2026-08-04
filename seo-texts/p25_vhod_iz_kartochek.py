# -*- coding: utf-8 -*-
"""Люди с карточек площадки — во вход обратного хода. Новый и большой источник имён.

ПОЧЕМУ ЭТО СЕЙЧАС ГЛАВНОЕ. Обратный ход исчерпан: 1 062 полных ФИО, спрошено 1 070, к
обходу ноль. Канал жив, ему нечего есть. А час назад я сама добыла 2 900 контактов с
карточек площадки, среди которых сотни людей с ИМЕНЕМ, но без личного мобильного — у
них городской, почта или вообще ничего. Это ровно та еда, которую канал ест: он ищет
личный номер по имени и предприятию.

То есть я добыла новый источник имён и не завела его в свой же основной канал. Это
третий случай за смену, когда два моих потока лежат рядом и не пересекаются (именной
канал с обратным ходом, канал номеров с потоком должностей, теперь эти). Правило,
которое из этого следует: КАЖДЫЙ НОВЫЙ ИСТОЧНИК ИМЁН ОБЯЗАН БЫТЬ ПРЕДЛОЖЕН КАЖДОМУ
КАНАЛУ, КОТОРЫЙ ЕСТ ИМЕНА. Иначе добыча оседает в файле, где её никто не спрашивает.

ЧТО БЕРЁТСЯ И ЧТО НЕТ. Берутся люди с полным ФИО, у которых личного мобильного нет
НИГДЕ (ни в этой строке, ни в другой строке того же файла). Не берутся: люди, у кого
мобильный уже есть — их искать незачем; строки без имени; имена, приведённые из
дательного падежа догадкой, если отчества нет — такое имя в кавычках ищется плохо и
жжёт общий пул.

ДОПИСЫВАЮ, А НЕ ПЕРЕЗАПИСЫВАЮ. Во входном файле лежат имена от 2-й сессии и мои
прежние. Затереть их значило бы выбросить чужую работу; собиратель входа всё равно
схлопнет дубли и посчитает, сколько человек названо двумя источниками независимо.
"""
import collections
import csv
import io
import json
import os
import re
import sqlite3

ISHODNIK = r'C:\sender\_ops\P25-TP-KARTOCHKI-LYUDI-3S.csv'
VHOD = r'C:\sender\_ops\3s_p25_vhod_iz_kartochek.csv'
csv.field_size_limit(10 ** 8)

FIO_POLNOE = re.compile(r'^[А-ЯЁ][а-яё]{2,}\s+[А-ЯЁ][а-яё]{2,}\s+'
                        r'[А-ЯЁ][а-яё]{2,}(?:ович|евич|ьевич|овна|евна|ьевна|ична)$')


def cifry(n):
    c = re.sub(r'\D', '', str(n or ''))
    return '7' + c[1:] if len(c) == 11 and c[0] in '78' else c


b = sqlite3.connect('file:C:/seostat/data/p25.db?mode=ro', uri=True)
nashi = {i: n for i, n in b.execute('select inn, coalesce(predpriyatie,"") from company')}
mesta = {i: m for i, m in b.execute('select inn, coalesce(mesto_po_summe,9999) from company')}

rows = list(csv.DictReader(open(ISHODNIK, encoding='utf-8-sig'), delimiter=';'))

# ПЕРВЫЙ ПРОХОД: у кого личный мобильный уже есть — по ВСЕМУ файлу, а не по строке.
# Человек может стоять в одной строке с почтой и в другой с мобильным; спрашивать его
# заново значит жечь общий пул за уже известное.
s_mobilnym = set()
for r in rows:
    if r.get('vid') == 'МОБИЛЬНЫЙ ЛИЧНЫЙ' and r.get('chelovek'):
        s_mobilnym.add(((r.get('inn') or '').strip(), r['chelovek'].strip().lower()))

sch = collections.Counter()
vidano, stroki = set(), []
for r in rows:
    chel = (r.get('chelovek') or '').strip()
    inn = (r.get('inn') or '').strip()
    if not chel:
        sch['контакт без имени — искать некого'] += 1
        continue
    if not FIO_POLNOE.match(chel):
        sch['имя без отчества — в кавычках ищется плохо'] += 1
        continue
    if (inn, chel.lower()) in s_mobilnym:
        sch['личный мобильный уже есть'] += 1
        continue
    k = (inn, chel.lower())
    if k in vidano:
        continue
    vidano.add(k)
    nash = bool(inn) and inn in nashi
    sch['В ОБХОД'] += 1
    if nash:
        sch['  из них на наших покупателях P25'] += 1
    stroki.append({
        'inn': inn, 'predpriyatie': nashi.get(inn) or r.get('predpriyatie', ''),
        'fio': chel, 'dolzhnost': r.get('dolzhnost_v_tekste', ''),
        'otkuda': 'карточка Tender.pro (%s)' % (r.get('rol_po_kartochke') or 'роль не названа'),
        'mesto_po_summe': mesta.get(inn, 9999) if nash else 9999,
    })

# Дороже те, кто у наших покупателей и выше по продажам: канал спрашивает сверху вниз.
stroki.sort(key=lambda s: s['mesto_po_summe'])
buf = io.StringIO()
w = csv.DictWriter(buf, fieldnames=['inn', 'predpriyatie', 'fio', 'dolzhnost', 'otkuda'],
                   delimiter=';', extrasaction='ignore')
w.writeheader()
w.writerows(stroki)
open(VHOD, 'w', encoding='utf-8-sig', newline='').write(buf.getvalue())

for s in stroki[:12]:
    print('  место %4s  %-30s %-30s %s' % (
        s['mesto_po_summe'] if s['mesto_po_summe'] < 9999 else '—',
        s['predpriyatie'][:30], s['fio'][:30], s['dolzhnost'][:20]))
for k, v in sch.most_common():
    print('REC %s\t%d' % (k, v))
print('ИТОГ ' + json.dumps({
    'новых имён во вход': len(stroki),
    'предприятий': len({s['inn'] for s in stroki if s['inn']}),
    'файл': os.path.basename(VHOD)}, ensure_ascii=False))
