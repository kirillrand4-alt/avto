# -*- coding: utf-8 -*-
"""Свёртка контактов с НАКОПЛЕНИЕМ ссылок: правило владельца «доказательств столько, сколько уникальных ссылок».

1-я сессия нашла: `kontakty_svod` — 11 351 контакт на 181 ИНН, 63 на предприятие, нужен
дедуп. Владелец уточнил, и это меняет смысл дедупа: **свёртка не выбрасывает, а копит.**
Один и тот же человек, найденный по пяти разным ссылкам, — это не пять мусорных строк и не
одна строка, а ОДИН контакт с ПЯТЬЮ доказательствами. Число уникальных ссылок и есть сила.

Ровно этим мы уже платили: из 773 пар «ИНН + номер» двумя независимыми разборами были
подтверждены 186, и все схлопывались в один ярлык — подтверждённое дважды становилось
неотличимо от подтверждённого однажды.

Ключ свёртки (канон P25): ИНН + 10 цифр номера. Для почты: ИНН + адрес в нижнем регистре.

Прибор считает: сколько строк, во что схлопывается, и сколько у скольких доказательств.
Читает базу со спутниками WAL — 1-я сессия предупредила, что без них видна часть таблиц.
Только чтение.
"""
import collections
import json
import os
import re
import sqlite3

BAZA = r'C:\seostat\drop\drop-storage\atlas_copco.db'


def desyat(t):
    c = re.sub(r'\D', '', str(t or ''))
    if len(c) == 11 and c[0] in '78':
        c = c[1:]
    return c if len(c) == 10 else ''


print('файл: %s, есть: %s' % (BAZA, os.path.exists(BAZA)))
for sput in ('-wal', '-shm'):
    p = BAZA + sput
    print('  спутник %s: %s' % (sput, os.path.getsize(p) if os.path.exists(p) else 'нет'))

cx = sqlite3.connect('file:%s?mode=ro' % BAZA.replace('\\', '/'), uri=True)
kol = [r[1] for r in cx.execute('pragma table_info(kontakty_svod)')]
print('\nkontakty_svod колонки: %s' % kol)
n = cx.execute('select count(*) from kontakty_svod').fetchone()[0]
print('строк: %d' % n)

sel = ','.join('"%s"' % k for k in kol)
pole_url = [k for k in kol if 'url' in k.lower() or 'ssyl' in k.lower() or k.lower() == 'source']
pole_tel = [k for k in kol if 'phone' in k.lower() or 'tel' in k.lower()]
pole_em = [k for k in kol if 'mail' in k.lower()]
print('поля: ссылка=%s телефон=%s почта=%s' % (pole_url, pole_tel, pole_em))

tel_ssylki = collections.defaultdict(set)
em_ssylki = collections.defaultdict(set)
tel_lyudi = collections.defaultdict(set)
sch = collections.Counter()
for r in cx.execute('select %s from kontakty_svod' % sel):
    d = dict(zip(kol, r))
    inn = str(d.get('inn') or '').strip()
    url = ''
    for k in pole_url:
        if d.get(k):
            url = str(d[k]).strip()
            break
    for k in pole_tel:
        c = desyat(d.get(k))
        if inn and c:
            tel_ssylki[(inn, c)].add(url or '(без ссылки)')
            if d.get('person'):
                tel_lyudi[(inn, c)].add(str(d['person']).strip())
            sch['строк с телефоном'] += 1
    for k in pole_em:
        e = str(d.get(k) or '').strip().lower()
        if inn and '@' in e:
            em_ssylki[(inn, e)].add(url or '(без ссылки)')
            sch['строк с почтой'] += 1
cx.close()

print('\n=== СВЁРТКА')
print('  строк всего                       %6d' % n)
for k, v in sch.most_common():
    print('  %-32s %6d' % (k, v))
print('  РАЗНЫХ телефонных контактов       %6d  (ИНН + 10 цифр)' % len(tel_ssylki))
print('  РАЗНЫХ почтовых контактов         %6d' % len(em_ssylki))

print('\n=== СКОЛЬКО ДОКАЗАТЕЛЬСТВ У КОНТАКТА (уникальных ссылок)')
for imya, d in (('телефон', tel_ssylki), ('почта', em_ssylki)):
    r = collections.Counter(len([s for s in v if s != '(без ссылки)']) for v in d.values())
    print('  --- %s' % imya)
    for k in sorted(r):
        print('      ссылок %-3d : контактов %5d' % (k, r[k]))
    bez = sum(1 for v in d.values() if v == {'(без ссылки)'})
    print('      БЕЗ ЕДИНОЙ ССЫЛКИ: %d' % bez)

print('\n=== ДЕСЯТЬ КОНТАКТОВ С САМЫМ БОЛЬШИМ ЧИСЛОМ ДОКАЗАТЕЛЬСТВ (глазами)')
for (inn, c), ss in sorted(tel_ssylki.items(), key=lambda x: -len(x[1]))[:10]:
    lyudi = tel_lyudi.get((inn, c)) or set()
    print('\n  ИНН %-12s +7%s   ссылок %d   имён %d: %s'
          % (inn, c, len([s for s in ss if s != '(без ссылки)']), len(lyudi),
             '; '.join(list(lyudi)[:3])[:90]))
    for s in list(ss)[:4]:
        print('      %s' % str(s)[:110])

print('\nИТОГ ' + json.dumps({'строк': n, 'разных телефонов': len(tel_ssylki),
                              'разных почт': len(em_ssylki)}, ensure_ascii=False))
