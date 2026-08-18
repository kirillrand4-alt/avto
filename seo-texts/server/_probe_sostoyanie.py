# -*- coding: utf-8 -*-
"""Жив ли работник проверки, включён ли цикл, сколько адресов группы без вердикта."""
import json
import os
import sqlite3
import subprocess
import sys
import time

sys.stdout.reconfigure(encoding='utf-8')
итог = {}
s = sqlite3.connect('file:%s?mode=ro' % r'C:/sender/sender.db', uri=True)
s.row_factory = sqlite3.Row
итог['настройки'] = {r['key']: str(r['value'])[:60] for r in s.execute(
    "select key, value from panel_settings where key like '%probe%'")}
итог['свежесть_вердиктов'] = [dict(r) for r in s.execute(
    "select substr(ts,1,13) chas, count(*) n from addr_probe "
    'group by 1 order by 1 desc limit 5')]
есть_вердикт = {str(r[0]).lower() for r in s.execute('select email from addr_probe')}
группа = []
for инн, em, ex in s.execute("select coalesce(inn,''), lower(coalesce(email,'')), "
                             "coalesce(extra_json,'') from recipients "
                             "where extra_json like '%Партия 935%'"):
    try:
        d = json.loads(ex) if ex.strip() else {}
    except Exception:  # noqa: BLE001
        d = {}
    if 'Партия 935' in [str(g) for g in (d.get('gruppy') or [])] and em:
        группа.append(em)
s.close()
без = sorted({e for e in группа if e not in есть_вердикт})
итог['адресов_в_группе'] = len(set(группа))
итог['без_вердикта'] = len(без)
итог['примеры_без_вердикта'] = без[:5]
# что лежит на дропе
env = {}
try:
    for l in open(r'C:\sender\server\runner-secrets.env', encoding='utf-8'):
        if '=' in l and not l.strip().startswith('#'):
            k, v = l.split('=', 1)
            env[k.strip()] = v.strip().strip('"').strip("'")
except Exception as e:  # noqa: BLE001
    итог['секреты'] = 'не прочитать: %s' % e
итог['дроп_настроен'] = bool(env.get('DROP_URL') and env.get('DROP_TOKEN'))
if итог['дроп_настроен']:
    p = subprocess.run(['curl', '-s', '-H', 'X-Drop-Token: ' + env['DROP_TOKEN'],
                        env['DROP_URL'].rstrip('/') + '/list'],
                       capture_output=True, text=True, timeout=90)
    try:
        файлы = json.loads(p.stdout or '[]')
    except Exception:  # noqa: BLE001
        файлы = p.stdout[:200]
    if isinstance(файлы, list):
        итог['на_дропе'] = [f for f in файлы if isinstance(f, str)
                            and ('probe' in f or f.startswith('vjob-'))][:8]
    else:
        итог['на_дропе'] = файлы
print(json.dumps(итог, ensure_ascii=False, indent=1)[:3000])
