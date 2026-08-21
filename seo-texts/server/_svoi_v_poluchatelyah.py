# -*- coding: utf-8 -*-
r"""Пять НАШИХ адресов среди получателей: писали ли уже и что будет, если напишем.

Письмо на собственный ящик рассылки — это не только пустой расход: входящее
попадёт к наблюдателю за почтой и может завестись как ответ, то есть как лид.
"""
import json
import sqlite3
import sys

sys.path.insert(0, r'C:\sender')
sys.path.insert(0, r'C:\sender\sender')
try:
    from sender import lid_ssylka as LS
except Exception:  # noqa: BLE001
    import lid_ssylka as LS

наши = LS.nashi_domeny()
s = sqlite3.connect('file:C:/sender/sender.db?mode=ro', uri=True, timeout=60)
s.row_factory = sqlite3.Row
итог = []
for r in s.execute("select id, email, coalesce(inn,'') inn, "
                   "coalesce(extra_json,'') ex from recipients"):
    if str(r['email'] or '').split('@')[-1].lower() not in наши:
        continue
    писем = s.execute('select count(*) from messages where recipient_id=?',
                      (r['id'],)).fetchone()[0]
    отправлено = s.execute("select count(*) from messages where recipient_id=? "
                           "and coalesce(status,'')='sent'", (r['id'],)).fetchone()[0]
    события = [x[0] for x in s.execute(
        'select distinct event_type from events where recipient_id=?', (r['id'],))]
    в_очереди = s.execute("select count(*) from confirm_reviews where "
                          "recipient_id=? and status='pending'",
                          (r['id'],)).fetchone()[0]
    итог.append({'id': r['id'], 'адрес': r['email'], 'инн': r['inn'],
                 'группы': r['ex'][:60], 'писем': писем, 'отправлено': отправлено,
                 'события': события, 'в_очереди_подтверждения': в_очереди})
стоп = [x[0] for x in s.execute("select value from suppression where scope='email'")]
s.close()
print(json.dumps({'наши_адреса_в_получателях': итог,
                  'уже_в_стоп_листе': [x for x in стоп
                                       if str(x).split('@')[-1].lower() in наши]},
                 ensure_ascii=False, indent=1)[:3000])
