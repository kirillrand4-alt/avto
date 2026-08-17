# -*- coding: utf-8 -*-
"""Загружена ли уже партия в панель: смотрим source='партия-935' и следы CSV."""
import glob
import json
import os
import sqlite3
import sys

sys.stdout.reconfigure(encoding='utf-8')
итог = {}
s = sqlite3.connect('file:%s?mode=ro' % r'C:/sender/sender.db', uri=True)
s.row_factory = sqlite3.Row
кол = [r[1] for r in s.execute('pragma table_info(recipients)')]
итог['партия-935_строк'] = s.execute(
    "select count(*) from recipients where source='партия-935'").fetchone()[0]
дата = next((k for k in ('created_at', 'added_at', 'updated_at') if k in кол), None)
if дата:
    итог['по_дате_' + дата] = [dict(r) for r in s.execute(
        "select substr(coalesce(%s,''),1,10) d, count(*) n from recipients "
        "where source='партия-935' group by 1 order by 1" % дата)]
итог['все_группы'] = [dict(r) for r in s.execute(
    "select coalesce(source,'(пусто)') g, count(*) n from recipients "
    'group by 1 order by n desc limit 10')]
s.close()
итог['csv_в_tmp'] = sorted(
    (os.path.basename(p), os.path.getsize(p)) for p in
    glob.glob(r'C:\sender\_tmp\*935*') + glob.glob(r'C:\sender\*935*'))
print(json.dumps(итог, ensure_ascii=False, indent=1))
