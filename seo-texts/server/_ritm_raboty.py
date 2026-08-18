# -*- coding: utf-8 -*-
"""Ритм работника: сколько вердиктов и в какие часы за последние трое суток."""
import json
import sqlite3
import sys

sys.stdout.reconfigure(encoding='utf-8')
s = sqlite3.connect('file:%s?mode=ro' % r'C:/sender/sender.db', uri=True)
ряд = [dict(zip(('час', 'сколько'), r)) for r in s.execute(
    "select substr(ts,1,13) h, count(*) n from addr_probe "
    "where ts >= '2026-08-16' group by 1 order by 1 desc limit 24")]
итог = {'по_часам': ряд}
итог['всего_за_сутки'] = s.execute(
    "select count(*) from addr_probe where ts >= '2026-08-18'").fetchone()[0]
итог['последний_вердикт'] = s.execute(
    'select max(ts) from addr_probe').fetchone()[0]
s.close()
print(json.dumps(итог, ensure_ascii=False, indent=1)[:2000])
