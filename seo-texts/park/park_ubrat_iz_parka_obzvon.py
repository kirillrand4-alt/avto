# -*- coding: utf-8 -*-
"""Убираю из парка тех, кто УЖЕ отображается в базе обзвона «Центробежные».

Просьба владельца: «из park убери центробежные которые есть в базе центробежных и
отображаются». Смысл понятен: парк — это ДОБОР, а не повтор. Если предприятие уже стоит в
очереди у продавца, показывать его в парке значит дважды звать на одну и ту же компанию.

Что считается «отображается» (замер на сервере, не предположение):

    назначено продавцам ........ 1 615
    из них есть в базе центробежных 1 597
    скрыто оператором ...........  931
    ОТОБРАЖАЕТСЯ ................  666   <- вот это множество и убираем

Убираю НЕ удалением: ставлю `v_obzvone=1`, и выдача парка их не показывает. Факты, ссылки и
контакты остаются на месте — если предприятие уберут из обзвона, оно вернётся в парк само.
"""
import json, os, sqlite3

D = os.path.dirname(os.path.abspath(__file__))
p = sqlite3.connect(os.path.join(D, 'park.db'))
c = p.cursor()
vidno = set(json.load(open(os.path.join(D, '_obzvon_vidno.json'), encoding='utf-8')))
if 'v_obzvone' not in [r[1] for r in c.execute('pragma table_info(fakt)')]:
    c.execute('alter table fakt add column v_obzvone integer default 0')
c.execute('update fakt set v_obzvone=0')
q = lambda s: c.execute(s).fetchone()[0]
bylo = q('select count(distinct inn) from fakt where v_parke=1')
sp = ','.join('?' * 900)
tronuto = 0
lst = sorted(vidno)
for i in range(0, len(lst), 900):
    pack = lst[i:i + 900]
    c.execute('update fakt set v_obzvone=1 where v_parke=1 and inn in (%s)'
              % ','.join('?' * len(pack)), pack)
    tronuto += c.rowcount
p.commit()
stalo = q('select count(distinct inn) from fakt where v_parke=1 and v_obzvone=0')
print('отображается в обзвоне ..... %d предприятий' % len(vidno))
print('фактов помечено ............ %d' % tronuto)
print('предприятий в парке: %d -> %d (убрано %d)' % (bylo, stalo, bylo - stalo))
print('пересечение парка и обзвона: %d' % q(
    'select count(distinct inn) from fakt where v_parke=1 and v_obzvone=1'))
p.close()
