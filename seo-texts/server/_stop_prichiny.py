# -*- coding: utf-8 -*-
"""Какие причины и scope уже используются в стоп-листе — чтобы не выдумывать свои."""
import json
import sqlite3
import sys

sys.stdout.reconfigure(encoding='utf-8')
s = sqlite3.connect('file:%s?mode=ro' % r'C:/sender/sender.db', uri=True)
итог = {'по_scope': [list(r) for r in s.execute(
    'select scope, count(*) from suppression group by 1 order by 2 desc')],
    'по_причинам': [list(r) for r in s.execute(
        'select scope, reason, count(*) n from suppression group by 1,2 '
        'order by n desc limit 12')]}
s.close()
try:
    import io, re
    t = io.open(r'C:\sender\sender\confirm.py', encoding='utf-8', errors='replace').read()
    m = re.search(r'STOPLIST_REASONS\s*=\s*\{.*?\}', t, re.S)
    итог['STOPLIST_REASONS'] = m.group(0)[:400] if m else 'не найдено'
except Exception as e:  # noqa: BLE001
    итог['STOPLIST_REASONS'] = str(e)[:80]
print(json.dumps(итог, ensure_ascii=False, indent=1))
