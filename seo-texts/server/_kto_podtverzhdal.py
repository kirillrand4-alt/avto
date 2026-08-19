# -*- coding: utf-8 -*-
"""Кто подтверждал письма: подписи в decided_by и сколько из них ушло."""
import json
import sqlite3
import sys

sys.stdout.reconfigure(encoding='utf-8')
s = sqlite3.connect('file:%s?mode=ro' % r'C:/sender/sender.db', uri=True)
s.row_factory = sqlite3.Row
итог = {}
итог['подписи'] = [dict(r) for r in s.execute(
    "select coalesce(decided_by,'(пусто)') кто, status, count(*) n, "
    'min(decided_at) с, max(decided_at) по from confirm_reviews '
    "where coalesce(decided_at,'')<>'' group by 1,2 order by n desc limit 12")]
итог['отправлено_по_дням'] = [dict(r) for r in s.execute(
    "select substr(event_ts,1,10) d, count(*) n from events "
    "where event_type='sent' group by 1 order by 1 desc limit 6")]
итог['режим_подтверждения'] = [dict(r) for r in s.execute(
    "select key, substr(coalesce(value,''),1,60) v from panel_settings "
    "where key like '%confirm%' or key like '%live%' or key like '%auto%'")]
s.close()
print(json.dumps(итог, ensure_ascii=False, indent=1, default=str)[:4000])
