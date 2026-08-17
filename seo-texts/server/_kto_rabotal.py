# -*- coding: utf-8 -*-
"""Кто и что делал в панели: действия по пользователям и решения по очереди."""
import json
import sqlite3
import sys

sys.stdout.reconfigure(encoding='utf-8')
s = sqlite3.connect('file:%s?mode=ro' % r'C:/sender/sender.db', uri=True)
s.row_factory = sqlite3.Row
итог = {}
итог['пользователи'] = [dict(r) for r in s.execute(
    'select id, coalesce(email,"") email, coalesce(role,"") role, '
    'coalesce(created_at,"") sozdan from users')]
итог['действия'] = [dict(r) for r in s.execute(
    "select actor_user_id kto, action, count(*) skolko, max(created_at) posledniy "
    'from audit_log group by 1,2 order by skolko desc limit 14')]
итог['решения_очереди'] = [dict(r) for r in s.execute(
    "select coalesce(decided_by,'(никто)') kto, status, count(*) skolko, "
    'max(decided_at) posledniy from confirm_reviews group by 1,2 order by skolko desc limit 12')]
итог['вердикты_целей'] = [dict(r) for r in s.execute(
    'select * from target_verdicts limit 3')]
итог['вердиктов_всего'] = s.execute('select count(*) from target_verdicts').fetchone()[0]
s.close()
print(json.dumps(итог, ensure_ascii=False, indent=1)[:3000])
