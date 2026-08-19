# -*- coding: utf-8 -*-
"""Точная хронология по трём адресам: когда подтвердили, когда ушло, когда вердикт."""
import json
import sqlite3
import sys
import time

sys.stdout.reconfigure(encoding='utf-8')
АДРЕСА = ('test@mail.ru', 'a.nosov@iat38.ru', 'shop@zavodsota.ru')
s = sqlite3.connect('file:%s?mode=ro' % r'C:/sender/sender.db', uri=True)
s.row_factory = sqlite3.Row
итог = {'сейчас_местное': time.strftime('%Y-%m-%d %H:%M'),
        'сейчас_utc': time.strftime('%Y-%m-%dT%H:%M', time.gmtime()), 'адреса': []}
for a in АДРЕСА:
    з = {'адрес': a}
    r = s.execute("select id, status, decided_by, decided_at, created_at "
                  "from confirm_reviews where lower(coalesce(email,''))=?",
                  (a,)).fetchone()
    if r:
        з['очередь'] = {'создано': r['created_at'], 'решено': r['decided_at'],
                        'статус': r['status'], 'кем': (r['decided_by'] or '')[:60]}
    m = s.execute("select id, status, coalesce(sent_at,'') sa, coalesce(created_at,'') ca "
                  'from messages where lower(coalesce(to_email,\'\'))=? '
                  'order by id desc limit 1', (a,)).fetchone() \
        if [x for x in s.execute('pragma table_info(messages)') if x[1] == 'to_email'] else None
    if m:
        з['письмо'] = dict(m)
    ev = [dict(x) for x in s.execute(
        "select event_type, event_ts from events where message_id in "
        "(select id from messages where lower(coalesce(to_email,''))=?) "
        'order by event_ts', (a,))] if m else []
    з['события'] = ev
    p = s.execute('select verdict, ts, coalesce(answer,\'\') otv from addr_probe '
                  'where lower(email)=?', (a,)).fetchone()
    if p:
        з['вердикт_пробы'] = {'что': p['verdict'], 'когда': p['ts'],
                              'ответ': p['otv'][:60]}
    итог['адреса'].append(з)
итог['колонки_messages'] = [r[1] for r in s.execute('pragma table_info(messages)')]
итог['колонки_events'] = [r[1] for r in s.execute('pragma table_info(events)')]
s.close()
print(json.dumps(итог, ensure_ascii=False, indent=1, default=str)[:4200])
