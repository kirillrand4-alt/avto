# -*- coding: utf-8 -*-
"""Люди моего канала «поиск-ЛПР-3с-песочница» без имени и без проверенной привязки.

Владелец открыл карточку предприятия и отметил в моём же источнике две вещи:

  * «Имя не установлено», начальник цеха, с пометкой «имя разобрано неверно, было:
    Начальник А.А.» — то есть мой разбор принял слово ДОЛЖНОСТИ за фамилию, кто-то это
    заметил и пометил, а карточка всё равно стоит в панели как человек;
  * «Ахмадишин Фаиз Фаикович», главный инженер, без пометки о проверке привязки, тогда
    как у соседнего Анисимова стоит «привязка проверена по ядру имени».

Прибор считает по базе панели, а не по снимку экрана: сколько людей моего источника
стоят без имени, сколько без проверенной привязки, и что у них в поле проверки.

ПОЧЕМУ ЭТО НЕ КОСМЕТИКА. Карточка «Имя не установлено» занимает место человека: она
показывается продавцу как ЛПР, по ней нельзя позвонить, и она же засчитывается в
«людей предприятия». Пустое имя — это не человек, а след ошибки разбора.
"""
import collections
import json
import re
import sqlite3

BAZY = (('centrifugal', 'file:C:/seostat/data/centrifugal.db?mode=ro'),
        ('p25', 'file:C:/seostat/data/p25.db?mode=ro'))
MOY = 'песочница'
# Слова, которые не могут быть фамилией: это должности и обращения.
NE_IMYA = re.compile(
    r'^(?:начальник|главн|директор|инженер|механик|энергетик|технолог|заместител|'
    r'руководител|специалист|ведущ|старш|мастер|бригадир|уважаем|контакт|ответственн)',
    re.I)
PUSTO = re.compile(r'^\s*(?:имя не установлено|не установлено|нет данных|—|-|\?)?\s*$', re.I)

for imya, put in BAZY:
    try:
        b = sqlite3.connect(put, uri=True)
        tablicy = [t for (t,) in b.execute("select name from sqlite_master where type='table'")]
    except Exception as e:  # noqa: BLE001
        print('%s: %s' % (imya, e))
        continue
    for t in tablicy:
        try:
            polya = [r[1] for r in b.execute('pragma table_info(%s)' % t)]
        except Exception:  # noqa: BLE001
            continue
        k_imya = [x for x in polya if re.search(r'\bname\b|fio|chelovek|imya', x, re.I)]
        k_ist = [x for x in polya if re.search(r'source|istoch|otkuda', x, re.I)]
        if not (k_imya and k_ist):
            continue
        sch = collections.Counter()
        primery = []
        try:
            stroki = list(b.execute('select %s from %s' % (','.join(polya), t)))
        except Exception:  # noqa: BLE001
            continue
        for r in stroki:
            z = dict(zip(polya, r))
            ist = ' '.join(str(z.get(k) or '') for k in k_ist)
            if MOY not in ist:
                continue
            nm = ' '.join(str(z.get(k) or '') for k in k_imya).strip()
            sch['всего людей моего источника'] += 1
            if PUSTO.match(nm):
                sch['БЕЗ ИМЕНИ — не человек, а след ошибки разбора'] += 1
                if len(primery) < 6:
                    primery.append(('без имени', nm[:30], ist[:100]))
            elif NE_IMYA.match(nm.split()[0] if nm.split() else ''):
                sch['имя начинается со слова ДОЛЖНОСТИ'] += 1
                if len(primery) < 6:
                    primery.append(('должность как имя', nm[:30], ist[:100]))
            if 'привязка проверена' in ist.lower():
                sch['  привязка проверена явно'] += 1
            elif 'привязка снята' in ist.lower():
                sch['  привязка снята явно'] += 1
            else:
                sch['  о привязке в источнике НИЧЕГО не сказано'] += 1
        if sch:
            print('=== %s.%s' % (imya, t))
            for vid, nm, ist in primery:
                print('    %-18s «%s»  ← %s' % (vid, nm, ist))
            for k, v in sch.most_common():
                print('    REC %s\t%d' % (k, v))
print('ИТОГ ' + json.dumps({'источник': MOY}, ensure_ascii=False))
