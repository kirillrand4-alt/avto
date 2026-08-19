# -*- coding: utf-8 -*-
"""Снять подтверждённое письмо на спам-ловушку: отправка туда бьёт по репутации."""
import json
import sqlite3
import sys
import time

sys.stdout.reconfigure(encoding='utf-8')
s = sqlite3.connect(r'C:\sender\sender.db', timeout=90)
s.row_factory = sqlite3.Row
стоп = {str(r[0]).lower(): r[1] for r in s.execute(
    "select value, coalesce(reason,'') from suppression where scope='email'")}
цели = []
for r in s.execute("select id, lower(coalesce(email,'')) em from confirm_reviews "
                   "where status in ('approved','pending')"):
    if r['em'] in стоп:
        цели.append((r['id'], r['em'], стоп[r['em']]))
ts = time.strftime('%Y-%m-%dT%H:%M:%S')
if '--primenit' in sys.argv:
    with s:
        for rid, _em, почему in цели:
            s.execute("update confirm_reviews set status='skipped', reason=?, "
                      'decided_by=?, decided_at=?, updated_at=? where id=?',
                      ('стоп-лист по адресу: %s' % почему,
                       'сверка очереди 19.08 (команда владельца)', ts, ts, rid))
итог = {'нашли': len(цели), 'снято': len(цели) if '--primenit' in sys.argv else 0,
        'адреса': [{'адрес': e, 'почему': п} for _i, e, п in цели]}
s.close()
print(json.dumps(итог, ensure_ascii=False, indent=1))
