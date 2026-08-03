# -*- coding: utf-8 -*-
"""Правило общего номера по ВСЕЙ панели, а не по своему файлу.

ПОВОД. Записи «обход сайта (3-я сессия)» надо проверить правилом чужого номера, но проверять
их по своему же файлу бессмысленно: номер приёмной, попавший к одному человеку в моей
выгрузке, выглядит там личным. Считать надо по всей таблице `person` панели — тогда видно,
что этот же номер стоит ещё у пяти предприятий.

Мера 2-й сессии, которую и воспроизводим: снять всё кроме цифр, взять последние десять,
сгруппировать по ним ИНН. Больше одного ИНН — номер личным не бывает.

Ничего не удаляется и не правится: печатается только разметка.
"""
import collections
import json
import re
import sqlite3

cx = sqlite3.connect(r'C:\seostat\data\centrifugal.db')
karta = collections.defaultdict(lambda: {'inn': set(), 'lyudi': set()})
vsego = 0
for inn, person, phone, src in cx.execute(
        "select coalesce(inn,''), coalesce(person,''), coalesce(phone,''), coalesce(source,'') "
        "from person where coalesce(phone,'') <> ''"):
    c = re.sub(r'\D', '', phone)
    if len(c) < 10:
        continue
    vsego += 1
    z = karta[c[-10:]]
    z['inn'].add(inn)
    z['lyudi'].add(person)

o = {'строк_с_телефоном': vsego, 'разных_номеров': len(karta),
     'номеров_у_2plus_предприятий': sum(1 for z in karta.values() if len(z['inn']) > 1)}

# Разрез по источникам: у кого доля общих номеров выше, тот канал и надо чинить первым.
po_ist = collections.Counter()
obshch_ist = collections.Counter()
for inn, person, phone, src in cx.execute(
        "select coalesce(inn,''), coalesce(person,''), coalesce(phone,''), coalesce(source,'') "
        "from person where coalesce(phone,'') <> ''"):
    c = re.sub(r'\D', '', phone)
    if len(c) < 10:
        continue
    po_ist[src] += 1
    if len(karta[c[-10:]]['inn']) > 1:
        obshch_ist[src] += 1
o['по_источникам'] = [[s, n, obshch_ist[s], f'{100 * obshch_ist[s] / n:.0f}%']
                      for s, n in po_ist.most_common(14)]
o['худшие_номера'] = [[k, len(z['inn']), len(z['lyudi'])]
                      for k, z in sorted(karta.items(), key=lambda x: -len(x[1]['inn']))[:8]]
print(json.dumps(o, ensure_ascii=False, indent=1))
