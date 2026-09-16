# -*- coding: utf-8 -*-
"""Замер под РАЗВОРОТ ЗАДАЧИ: идём от события, а не от компрессора.

Владелец меняет точку входа: тендеры не нужны, нужно событие, желательно на ранней стадии.
Прежде чем писать «чего нет», надо померить, что у нас вообще устроено под событие:
есть ли у сигнала стадия, адрес, регион, идентификатор проекта; сшиваются ли сообщения об
одном проекте; и есть ли в базе люди тех ролей, которые решают НА СТАДИИ ПРОЕКТА, а не при
эксплуатации.

Контроль: ролевой запрос по выдуманному слову обязан дать 0 — иначе поиск ролей не
различает.
"""
import re
import sqlite3

db = sqlite3.connect(r'C:\sender\enrich.db')
c = db.cursor()

print('### 1. Устройство таблицы signals: что в ней ЕСТЬ и чего в ней НЕТ\n')
kol = [x[1] for x in c.execute('pragma table_info(signals)').fetchall()]
print('  колонки: %s' % ', '.join(kol))
NUZHNO = ['stadiya', 'stage', 'proekt', 'project', 'region', 'subjekt', 'adres', 'address',
          'kadastr', 'data_sobytiya', 'event_date', 'srok', 'deadline', 'podryadchik',
          'proektirovshchik', 'zastroyshchik']
net = [k for k in NUZHNO if k not in kol]
print('  НЕТ полей под событие: %s' % ', '.join(net))

vsego = c.execute('select count(*) from signals').fetchone()[0]
s_inn = c.execute("select count(*) from signals where inn is not null and inn<>''").fetchone()[0]
raznyh = c.execute("select count(distinct inn) from signals where inn is not null and inn<>''").fetchone()[0]
print('\n  сигналов всего ................. %d' % vsego)
print('  с ИНН .......................... %d' % s_inn)
print('  БЕЗ ИНН (событие есть, чьё — нет) %d' % (vsego - s_inn))
print('  разных предприятий ............. %d' % raznyh)
print('  в среднем сигналов на ИНН ...... %.1f' % (s_inn / max(raznyh, 1)))

print('\n### 2. Сшивается ли один проект из разных источников\n')
r = c.execute("""select inn, count(*) n, count(distinct source) ist
                 from signals where inn is not null and inn<>''
                 group by inn having n>1 order by n desc limit 10""").fetchall()
print('  ИНН с несколькими сигналами (топ-10): inn / сигналов / разных источников')
for inn, n, ist in r:
    print('     %-13s %3d %3d' % (inn, n, ist))
mnogo = c.execute("""select count(*) from (select inn from signals
                     where inn is not null and inn<>'' group by inn having count(*)>1)""").fetchone()[0]
print('  предприятий с >1 сигналом: %d' % mnogo)
dvumya = c.execute("""select count(*) from (select inn from signals
                      where inn is not null and inn<>'' group by inn
                      having count(distinct source)>1)""").fetchone()[0]
print('  из них подтверждённых ДВУМЯ и более источниками: %d' % dvumya)

print('\n### 3. Даты: дата новости есть, а дата СОБЫТИЯ?\n')
print('  ts (когда мы взяли): %s' % str(c.execute('select min(ts), max(ts) from signals').fetchone()))
est_data_v_tekste = c.execute(
    "select count(*) from signals where what like '%20[0-9][0-9] г%' or what like '%к 20%'").fetchone()[0]
print('  строк, где дата события угадывается только из текста: %d' % est_data_v_tekste)

print('\n### 4. hotness — чем сейчас меряется приоритет\n')
for h, n in c.execute('select hotness, count(*) from signals group by 1 order by 2 desc limit 10').fetchall():
    print('     hotness=%-8s %5d' % (str(h)[:8], n))

print('\n### 5. РОЛИ: есть ли у нас люди СТАДИИ ПРОЕКТА, а не эксплуатации\n')
RANNIE = [('директор по развитию', r'развити'), ('капитальное строительство / УКС', r'капитальн|УКС|капстро'),
          ('руководитель проекта', r'руководител\w* проект|менеджер проект|ГИП|главн\w* инженер проект'),
          ('инвестиции', r'инвестиц'), ('технический заказчик / служба заказчика', r'заказчик'),
          ('главный энергетик (для сравнения)', r'энергетик'),
          ('снабжение (для сравнения)', r'снабжен|закупк'),
          ('КОНТРОЛЬ: выдуманная роль', r'щварцкопфер')]
for tabl, pole in (('people', 'role'), ('contacts', 'role')):
    try:
        vsego_r = c.execute('select count(*) from %s' % tabl).fetchone()[0]
    except Exception as e:  # noqa: BLE001
        print('  таблица %s недоступна: %s' % (tabl, str(e)[:60]))
        continue
    print('  --- %s, строк %d' % (tabl, vsego_r))
    znach = c.execute('select %s, count(*) from %s group by 1 order by 2 desc' % (pole, tabl)).fetchall()
    for imya, pat in RANNIE:
        rx = re.compile(pat, re.I)
        n = sum(k for z, k in znach if z and rx.search(str(z)))
        print('     %-42s %5d' % (imya, n))

print('\n### 6. Есть ли вообще таблица под проекты/стадии\n')
tabl = [r[0] for r in c.execute("select name from sqlite_master where type='table'").fetchall()]
nash = [t for t in tabl if re.search(r'proekt|project|stadi|stage|sobyt|event', t, re.I)]
print('  таблиц про проект/стадию/событие: %s' % (', '.join(nash) or 'НЕТ НИ ОДНОЙ'))
print('  всего таблиц в базе: %d' % len(tabl))
