# -*- coding: utf-8 -*-
"""41 751 строка `atlas_copco.db/tenders` без ссылки. Смотрю, чем их МОЖНО доказать.

Поток парка отбросил их по правилу владельца «факт доказывается ссылкой». Попытка собрать
ссылку из номера заключения ЭПБ провалилась: у 40 123 строк номера документа нет. Но это
был вопрос про ОДИН вид номера. У закупки может быть свой — реестровый номер извещения ЕИС
(11-25 цифр), и из него ссылка строится прямо.

Прежде чем писать сборщик, смотрю на сами колонки: что в них лежит, у скольких строк есть
что-то похожее на реестровый номер, и как выглядит десяток строк живьём. Ноль здесь тоже
будет ответом — но ответом ПРО КОЛОНКИ, а не про то, что данных нет.

Только чтение. Числа в КОНЦЕ.
"""
import collections
import os
import re
import sqlite3

BAZA = r'C:\seostat\drop\drop-storage\atlas_copco.db'
REESTR = re.compile(r'\b(\d{11}|\d{19}|\d{23})\b')
URL = re.compile(r'https?://')

cx = sqlite3.connect('file:%s?mode=ro' % BAZA.replace('\\', '/'), uri=True)
kol = [r[1] for r in cx.execute('pragma table_info("tenders")')]
print('########## КОЛОНКИ tenders')
print('  ' + ', '.join(kol))

zapoln = collections.Counter()
est_reestr, bez_ssylki, vsego = 0, 0, 0
primery = []
for r in cx.execute('select %s from tenders' % ','.join('"%s"' % k for k in kol)):
    d = dict(zip(kol, r))
    vsego += 1
    stroka = ' '.join(str(v) for v in r if v is not None)
    if URL.search(stroka):
        continue
    bez_ssylki += 1
    for k in kol:
        if str(d.get(k) or '').strip():
            zapoln[k] += 1
    if REESTR.search(stroka):
        est_reestr += 1
        if len(primery) < 8:
            primery.append(' | '.join('%s=%s' % (k, str(d[k])[:40]) for k in kol
                                      if str(d.get(k) or '').strip())[:300])
cx.close()

print('\n########## ВОСЕМЬ СТРОК БЕЗ ССЫЛКИ, ЖИВЬЁМ')
for p in primery:
    print('  ' + p)
print('\n########## ЧИСЛА')
print('  строк всего            %7d' % vsego)
print('  из них без ссылки      %7d' % bez_ssylki)
print('  есть реестровый номер  %7d' % est_reestr)
print('  --- чем заполнены строки без ссылки')
for k, v in zapoln.most_common(14):
    print('     %-28s %7d' % (k, v))
print('ИТОГ {"без ссылки": %d, "с реестровым номером": %d}' % (bez_ssylki, est_reestr))
