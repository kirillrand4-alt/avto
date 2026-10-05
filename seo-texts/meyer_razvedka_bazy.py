# -*- coding: utf-8 -*-
"""companies 169 790 + phone_contacts 777 736 с person/role/source_url — вот она, база.

Моя ошибка названа: я считала phone_contacts «телефонами компаний» и не посмотрела, что
там есть ИМЯ ЧЕЛОВЕКА, РОЛЬ и ССЫЛКА НА ИСТОЧНИК. Из-за этого первый сбор под Мейер дал
одного названного человека на 43 559 компаний и выглядел как приговор данным, а был
приговором моему запросу.
"""
import sqlite3

E = sqlite3.connect(r'C:\sender\enrich.db').cursor()

print('########## companies: заполненность')
n = E.execute('select count(*) from companies').fetchone()[0]
for p in ('inn', 'name', 'division', 'okved', 'region', 'site', 'activity',
          'best_email', 'phones', 'verified', 'is_competitor', 'pxr'):
    k = E.execute('select count(*) from companies where "%s" is not null and trim("%s")<>""'
                  % (p, p)).fetchone()[0]
    print('    %-14s %7d из %d (%.0f%%)' % (p, k, n, 100.0 * k / n))
print('    division: %s' % '; '.join(
    '%s=%d' % (a, b) for a, b in E.execute(
        'select division, count(*) from companies group by 1 order by 2 desc limit 6')))

print('\n########## phone_contacts: заполненность')
m = E.execute('select count(*) from phone_contacts').fetchone()[0]
for p in ('inn', 'phone', 'person', 'role', 'source', 'source_url'):
    k = E.execute('select count(*) from phone_contacts where "%s" is not null and trim("%s")<>""'
                  % (p, p)).fetchone()[0]
    print('    %-12s %7d из %d (%.0f%%)' % (p, k, m, 100.0 * k / m))
print('    разных ИНН: %d' % E.execute('select count(distinct inn) from phone_contacts').fetchone()[0])
print('    ИНН, где есть ИМЯ человека: %d' % E.execute(
    'select count(distinct inn) from phone_contacts where person is not null and trim(person)<>""').fetchone()[0])
print('    источники (топ-8): %s' % '; '.join(
    '%s=%d' % (str(a)[:28], b) for a, b in E.execute(
        'select source, count(*) from phone_contacts group by 1 order by 2 desc limit 8')))
print('    роли (топ-10): %s' % '; '.join(
    '%s=%d' % (str(a)[:22], b) for a, b in E.execute(
        'select role, count(*) from phone_contacts where role is not null and trim(role)<>"" '
        'group by 1 order by 2 desc limit 10')))

print('\n########## ТРИ ЖИВЫЕ СТРОКИ phone_contacts С ИМЕНЕМ')
pol = [r[1] for r in E.execute('PRAGMA table_info(phone_contacts)')]
for row in E.execute('select * from phone_contacts where person is not null and trim(person)<>"" '
                     'and source_url is not null and trim(source_url)<>"" limit 3'):
    print('  ---')
    for k, v in zip(pol, row):
        if v not in (None, ''):
            print('      %-12s %s' % (k, str(v)[:110]))

print('\n########## ГЛАВНОЕ: ШЕСТЬ СЕГМЕНТОВ ПО companies.okved И ЛЮДИ ПО НИМ')
SEG = {
    '1 экспортёры (опт зерна/продуктов)': ['46.21', '46.31', '46.32', '46.33', '46.36', '46.38', '46.17'],
    '2 семеноводы': ['01.64', '01.11', '01.13.52', '01.25.2'],
    '3 пищевые (10.*)': ['10.'],
    '4 элеваторы': ['52.10.3', '01.63', '10.61'],
    '5 орехи': ['10.39.2', '01.25.3'],
    '6 ягоды': ['01.25.1', '10.32'],
}
for imya, kody in SEG.items():
    usl = ' or '.join(['okved like ?'] * len(kody))
    inn = {str(r[0]) for r in E.execute(
        'select inn from companies where %s' % usl, [k + '%' for k in kody])}
    if not inn:
        print('    %-36s 0' % imya)
        continue
    sp = ','.join('"%s"' % i for i in list(inn)[:900])
    lyudi = E.execute('select count(distinct inn) from phone_contacts where person is not null '
                      'and trim(person)<>"" and inn in (%s)' % sp).fetchone()[0]
    tel = E.execute('select count(distinct inn) from phone_contacts where inn in (%s)' % sp).fetchone()[0]
    print('    %-36s компаний %6d · (на выборке 900: с ИМЕНЕМ %3d, с телефоном %3d)'
          % (imya, len(inn), lyudi, tel))
