# -*- coding: utf-8 -*-
"""Два отправленных письма целиком — планка, с которой сравниваю очередь.

Прошлый прогон напечатал их первыми, и хвост раннера их съел: он хранит КОНЕЦ вывода.
Здесь ничего, кроме них, не печатается.
"""
import sqlite3

cs = sqlite3.connect('file:C:/sender/sender.db?mode=ro', uri=True)
kol = [r[1] for r in cs.execute('pragma table_info(confirm_reviews)')]
for r in cs.execute('select %s from confirm_reviews where status="sent" order by id desc limit 3'
                    % ','.join('"%s"' % k for k in kol)):
    d = dict(zip(kol, r))
    print('\n\n===== ОТПРАВЛЕННОЕ #%s -> %s   ИНН %s'
          % (d.get('id'), d.get('email'), d.get('inn')))
    print('ТЕМА: %s' % d.get('subject'))
    print(str(d.get('body') or '')[:1500])
cs.close()
print('\nИТОГ {"напечатано": 3}')
