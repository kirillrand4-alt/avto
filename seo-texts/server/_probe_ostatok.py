# -*- coding: utf-8 -*-
"""Лёгкий счётчик: сколько адресов партии ещё без вердикта (без Store/Config)."""
import json
import sqlite3
import sys

sys.stdout.reconfigure(encoding='utf-8')
s = sqlite3.connect('file:%s?mode=ro' % r'C:/sender/sender.db', uri=True)
верд = {str(r[0]).lower() for r in s.execute('select email from addr_probe')}
всего = без = 0
for em, ex in s.execute("select lower(coalesce(email,'')), coalesce(extra_json,'') "
                        "from recipients where extra_json like '%Партия 935%'"):
    if not em:
        continue
    try:
        d = json.loads(ex) if ex.strip() else {}
    except Exception:  # noqa: BLE001
        continue
    if 'Партия 935' not in [str(g) for g in (d.get('gruppy') or [])]:
        continue
    всего += 1
    if em not in верд:
        без += 1
посл = s.execute('select max(ts) from addr_probe').fetchone()[0]
s.close()
print(json.dumps({'в_группе': всего, 'без_вердикта': без,
                  'последний_вердикт_utc': посл}, ensure_ascii=False))
