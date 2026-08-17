# -*- coding: utf-8 -*-
"""Свежие отбивки: баунсы и прочие ответы почтовых серверов за последние сутки."""
import json
import sqlite3
import sys
import time

sys.stdout.reconfigure(encoding='utf-8')
s = sqlite3.connect('file:%s?mode=ro' % r'C:/sender/sender.db', uri=True)
s.row_factory = sqlite3.Row
порог = time.strftime('%Y-%m-%dT%H:%M:%S', time.localtime(time.time() - 30 * 3600))
итог = {'считаем_с': порог, 'всего_событий_за_сутки': 0, 'по_типам': {}, 'отбивки': []}
for r in s.execute("select * from events where event_ts > ? order by id desc", (порог,)):
    итог['всего_событий_за_сутки'] += 1
    итог['по_типам'][r['event_type']] = итог['по_типам'].get(r['event_type'], 0) + 1
    if r['event_type'] in ('sent', 'open', 'click'):
        continue
    try:
        d = json.loads(r['detail_json'] or '{}')
    except Exception:
        d = {}
    dsn = d.get('dsn') or {}
    пол = s.execute("select coalesce(email,'') email, coalesce(inn,'') inn, "
                    "coalesce(company_name,'') name, coalesce(source,'') istochnik "
                    "from recipients where id=?", (r['recipient_id'],)).fetchone()
    итог['отбивки'].append({
        'когда': r['event_ts'][:19], 'тип': r['event_type'],
        'ящик': r['mailbox_id'], 'кампания': r['campaign_id'],
        'кому': (dsn.get('failed') or [пол['email'] if пол else ''])[:1],
        'компания': (пол['name'][:40] if пол else ''),
        'инн': (пол['inn'] if пол else ''),
        'откуда_адрес': (пол['istochnik'] if пол else ''),
        'ответ_сервера': (dsn.get('diagnostic') or '')[:90],
        'код': dsn.get('smtp_code'), 'вердикт': dsn.get('verdict', ''),
        'тема_письма': (d.get('subject') or d.get('headers', {}).get('Subject') or '')[:60]})
s.close()
итог['отбивок_показано'] = len(итог['отбивки'])
итог['отбивки'] = итог['отбивки'][:12]
print(json.dumps(итог, ensure_ascii=False, indent=1)[:3400])
