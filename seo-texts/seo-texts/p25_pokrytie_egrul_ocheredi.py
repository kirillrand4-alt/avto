# -*- coding: utf-8 -*-
"""Покрытие ЕГРЮЛ по очереди: подтверждаю число 2-й сессии и смотрю, чем прогон делать.

2-я сессия: «201 из 221 — реквизитов нет, и это ПОКРЫТИЕ, а не брак: выписку по этим ИНН
просто не тянули». Если так, то графа B заперта не ошибками, а одним невыполненным
прогоном — и это самая дешёвая работа с самым большим эффектом за всю смену.

Проверяю своим прибором, потому что число чужое и крупное:
    сколько ИНН в очереди, у скольких есть строка в `requisites`, у скольких ЕГРЮЛ-почта;
    есть ли на сервере токен dadata и в каком виде (значение НЕ печатаю, только факт).

Только чтение.
"""
import collections
import json
import os
import re
import sqlite3
import sys

SENDER, ENRICH = r'C:\sender\sender.db', r'C:\sender\enrich.db'

cs = sqlite3.connect('file:%s?mode=ro' % SENDER.replace('\\', '/'), uri=True)
inn_ochered = collections.Counter()
for st, inn in cs.execute('select status, inn from confirm_reviews'):
    if inn:
        inn_ochered[str(inn).strip()] += 1
pend = set(str(i).strip() for (i,) in cs.execute(
    'select inn from confirm_reviews where status="pending" and inn is not null'))
cs.close()

ce = sqlite3.connect('file:%s?mode=ro' % ENRICH.replace('\\', '/'), uri=True)
req = set(str(i).strip() for (i,) in ce.execute('select inn from requisites where inn is not null'))
vsego_req = len(req)
komp = ce.execute('select count(*) from companies').fetchone()[0]
kol_r = [r[1] for r in ce.execute('pragma table_info(requisites)')]
ce.close()

print('=== ПОКРЫТИЕ ЕГРЮЛ')
print('  компаний в базе                 %d' % komp)
print('  строк в requisites              %d  (%.0f%% базы)' % (vsego_req, 100.0 * vsego_req / max(1, komp)))
print('  разных ИНН в очереди            %d' % len(inn_ochered))
print('  из них pending                  %d' % len(pend))
print('  ИНН очереди С выпиской          %d' % len(set(inn_ochered) & req))
print('  ИНН очереди БЕЗ выписки         %d' % len(set(inn_ochered) - req))
print('  pending С выпиской              %d' % len(pend & req))
print('  pending БЕЗ выписки             %d' % len(pend - req))

print('\n=== ЧЕМ ДЕЛАТЬ ПРОГОН: токен dadata')
est = []
for k in os.environ:
    if 'DADATA' in k.upper():
        est.append('%s (длина %d)' % (k, len(os.environ[k])))
print('  в окружении: %s' % (est or 'НЕТ'))
for put in (r'C:\sender\server\runner-secrets.env', r'C:\sender\panel.env'):
    if os.path.exists(put):
        t = open(put, encoding='utf-8', errors='replace').read()
        naydeno = re.findall(r'^\s*([A-Z_]*DADATA[A-Z_]*)\s*=', t, re.M)
        print('  %s: ключи с DADATA -> %s' % (put, naydeno or 'нет'))

print('\n=== ПЕРВЫЕ 20 ИНН ОЧЕРЕДИ БЕЗ ВЫПИСКИ (вход прогона)')
for i in sorted(pend - req)[:20]:
    print('   %s' % i)
print('\nИТОГ ' + json.dumps({'ИНН очереди': len(inn_ochered),
                              'pending': len(pend),
                              'с выпиской': len(pend & req),
                              'без выписки': len(pend - req),
                              'токен dadata': bool(est)}, ensure_ascii=False))
