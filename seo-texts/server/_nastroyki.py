# -*- coding: utf-8 -*-
"""Настройки панели: нет ли выгрузки на другой VPS/инстанс для проверки."""
import json
import sqlite3
import sys

sys.stdout.reconfigure(encoding='utf-8')
s = sqlite3.connect('file:%s?mode=ro' % r'C:/sender/sender.db', uri=True)
s.row_factory = sqlite3.Row
итог = {'колонки': [r[1] for r in s.execute('pragma table_info(panel_settings)')]}
строки = [dict(r) for r in s.execute('select * from panel_settings limit 40')]
итог['настройки'] = [{k: (str(v)[:90] if v is not None else None) for k, v in r.items()}
                     for r in строки]
s.close()
print(json.dumps(итог, ensure_ascii=False, indent=1)[:3000])
