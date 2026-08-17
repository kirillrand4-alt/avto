# -*- coding: utf-8 -*-
"""Откуда в панели «Партия 935 (920)» при 757 строках source='партия-935'.

Смотрим все таблицы sender.db: где живёт понятие «группа», как считается 920,
и почему у 756 строк created_at сегодняшний.
"""
import json
import sqlite3
import sys

sys.stdout.reconfigure(encoding='utf-8')
s = sqlite3.connect('file:%s?mode=ro' % r'C:/sender/sender.db', uri=True)
s.row_factory = sqlite3.Row
итог = {}
итог['таблицы'] = [r[0] for r in s.execute(
    "select name from sqlite_master where type='table' order by 1")]
# где упоминается 935
for t in итог['таблицы']:
    кол = [r[1] for r in s.execute('pragma table_info(%s)' % t)]
    тексты = [k for k in кол if any(x in k for x in
              ('name', 'source', 'group', 'title', 'batch', 'label'))]
    for k in тексты:
        try:
            n = s.execute("select count(*) from %s where %s like '%%935%%'"
                          % (t, k)).fetchone()[0]
        except Exception:  # noqa: BLE001
            continue
        if n:
            итог.setdefault('где_935', []).append({'т': t, 'к': k, 'n': n})
# состав по updated/created у партия-935
кол = [r[1] for r in s.execute('pragma table_info(recipients)')]
итог['колонки_recipients'] = кол
поля = [k for k in ('created_at', 'updated_at', 'status', 'division') if k in кол]
итог['партия_935_срез'] = [dict(r) for r in s.execute(
    "select %s, count(*) n from recipients where source='партия-935' "
    'group by %s order by n desc limit 8'
    % (','.join('substr(coalesce(%s,\'\'),1,10) %s' % (k, k) for k in поля),
       ','.join(str(i + 1) for i in range(len(поля)))))]
s.close()
print(json.dumps(итог, ensure_ascii=False, indent=1)[:5200])
