# -*- coding: utf-8 -*-
"""Проверка целей работником: таблица target_verdicts и активность пользователей."""
import json
import sqlite3
import sys

sys.stdout.reconfigure(encoding='utf-8')
s = sqlite3.connect('file:%s?mode=ro' % r'C:/sender/sender.db', uri=True)
s.row_factory = sqlite3.Row
итог = {}
итог['колонки'] = [r[1] for r in s.execute('pragma table_info(target_verdicts)')]
итог['всего'] = s.execute('select count(*) from target_verdicts').fetchone()[0]
try:
    итог['по_статусам'] = [dict(r) for r in s.execute(
        'select verdict, count(*) skolko from target_verdicts group by 1 order by skolko desc')]
except Exception as e:  # noqa: BLE001
    итог['по_статусам_ошибка'] = str(e)[:80]
итог['последние'] = [dict(r) for r in s.execute(
    'select * from target_verdicts limit 3')]
итог['колонки_users'] = [r[1] for r in s.execute('pragma table_info(users)')]
итог['колонки_audit'] = [r[1] for r in s.execute('pragma table_info(audit_log)')]
итог['аудит_последние'] = [dict(r) for r in s.execute('select * from audit_log limit 3')]
s.close()
print(json.dumps(итог, ensure_ascii=False, indent=1)[:3000])
