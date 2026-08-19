# -*- coding: utf-8 -*-
"""Что проба говорила про отбившиеся адреса и что вообще за 441 отправка вчера."""
import json
import sqlite3
import sys

sys.stdout.reconfigure(encoding='utf-8')
s = sqlite3.connect('file:%s?mode=ro' % r'C:/sender/sender.db', uri=True)
s.row_factory = sqlite3.Row
итог = {}
# 1. отбившиеся адреса и их вердикт пробы
адреса = []
for r in s.execute("select detail_json from events where event_type='bounce' "
                   "and event_ts >= '2026-08-17'"):
    try:
        d = json.loads(r['detail_json'] or '{}')
    except Exception:  # noqa: BLE001
        continue
    for a in ((d.get('dsn') or {}).get('failed') or []):
        адреса.append(str(a).lower())
сверка = []
for a in sorted(set(адреса)):
    r = s.execute('select verdict, code, coalesce(answer,\'\') otv, ts from addr_probe '
                  'where lower(email)=?', (a,)).fetchone()
    сверка.append({'адрес': a, 'вердикт_пробы': (r['verdict'] if r else 'не проверялся'),
                   'ответ_пробы': (r['otv'][:60] if r else '')})
итог['отбившиеся_и_что_говорила_проба'] = сверка
счёт = {}
for x in сверка:
    счёт[x['вердикт_пробы']] = счёт.get(x['вердикт_пробы'], 0) + 1
итог['свод'] = счёт
# 2. природа отправок: через очередь подтверждения или прогрев
итог['отправок_по_кампаниям'] = [dict(r) for r in s.execute(
    "select campaign_id, count(*) n from events where event_type='sent' "
    "and event_ts >= '2026-08-18' group by 1 order by n desc limit 6")]
итог['подтверждений_оператором'] = [dict(r) for r in s.execute(
    "select status, count(*) n from confirm_reviews "
    "where coalesce(decided_at,'') >= '2026-08-18' group by 1 order by n desc")]
итог['прогрев_состояние'] = [dict(r) for r in s.execute(
    'select * from warmup_state limit 3')] if s.execute(
    "select count(*) from sqlite_master where name='warmup_state'").fetchone()[0] else []
s.close()
print(json.dumps(итог, ensure_ascii=False, indent=1, default=str)[:4000])
