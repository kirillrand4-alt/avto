# -*- coding: utf-8 -*-
"""Выложить на дроп список «неясных» адресов партии — для перепроверки на VPS."""
import json
import sqlite3
import subprocess
import sys

sys.stdout.reconfigure(encoding='utf-8')
ГРУППА = 'Партия 935'
s = sqlite3.connect('file:%s?mode=ro' % r'C:/sender/sender.db', uri=True)
неясно = {str(r[0]).lower() for r in s.execute(
    "select email from addr_probe where verdict='неясно'")}
наши = []
for em, ex in s.execute("select lower(coalesce(email,'')), coalesce(extra_json,'') "
                        'from recipients where extra_json like ?',
                        ('%' + ГРУППА + '%',)):
    if not em or em not in неясно:
        continue
    try:
        d = json.loads(ex) if ex.strip() else {}
    except Exception:  # noqa: BLE001
        continue
    if ГРУППА in [str(g) for g in (d.get('gruppy') or [])]:
        наши.append(em)
s.close()
наши = sorted(set(наши))
env = {}
for l in open(r'C:\sender\server\runner-secrets.env', encoding='utf-8'):
    if '=' in l and not l.strip().startswith('#'):
        k, v = l.split('=', 1)
        env[k.strip()] = v.strip().strip('"').strip("'")
данные = json.dumps(наши, ensure_ascii=False)
p = subprocess.run(['curl', '-s', '-X', 'PUT', '-H', 'X-Drop-Token: ' + env['DROP_TOKEN'],
                    '--data-binary', '@-',
                    env['DROP_URL'].rstrip('/') + '/probe-pereproverka.json'],
                   input=данные, capture_output=True, text=True, timeout=180)
print(json.dumps({'неясных_в_партии': len(наши), 'ответ_дропа': (p.stdout or '')[:120],
                  'примеры': наши[:4]}, ensure_ascii=False, indent=1))
