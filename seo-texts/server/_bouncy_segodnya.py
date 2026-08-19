# -*- coding: utf-8 -*-
"""Отбивки за сегодня: кому, от кого, с какой причиной."""
import json
import sqlite3
import sys

sys.stdout.reconfigure(encoding='utf-8')
s = sqlite3.connect('file:%s?mode=ro' % r'C:/sender/sender.db', uri=True)
s.row_factory = sqlite3.Row
итог = {}
итог['по_дням'] = [dict(r) for r in s.execute(
    "select substr(event_ts,1,10) d, event_type t, count(*) n from events "
    "where event_ts >= '2026-08-17' group by 1,2 order by 1 desc, n desc limit 12")]
строки = [dict(r) for r in s.execute(
    "select id, message_id, recipient_id, campaign_id, mailbox_id, provider, "
    "event_ts, detail_json from events where event_type='bounce' "
    "and event_ts >= '2026-08-18' order by event_ts desc limit 40")]
итог['отбивок'] = len(строки)
разбор = []
причины = {}
for r in строки:
    try:
        d = json.loads(r['detail_json'] or '{}')
    except Exception:  # noqa: BLE001
        d = {}
    dsn = d.get('dsn') or {}
    диаг = str(dsn.get('diagnostic') or '')[:150]
    кому = (dsn.get('failed') or [''])[0]
    вердикт = str(dsn.get('verdict') or '')
    код = dsn.get('smtp_code')
    ключ = '%s %s' % (код or '?', вердикт or '?')
    причины[ключ] = причины.get(ключ, 0) + 1
    if len(разбор) < 12:
        разбор.append({'когда': r['event_ts'][:16], 'ящик': r['mailbox_id'],
                       'кому': кому, 'код': код, 'вердикт': вердикт,
                       'ответ': диаг})
итог['по_причинам'] = dict(sorted(причины.items(), key=lambda kv: -kv[1]))
итог['примеры'] = разбор
s.close()
print(json.dumps(итог, ensure_ascii=False, indent=1)[:4500])
