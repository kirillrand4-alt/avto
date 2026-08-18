# -*- coding: utf-8 -*-
"""Жив ли дожим, что в задании, и сколько там НАШИХ непроверенных."""
import io
import json
import os
import sqlite3
import subprocess
import sys

sys.stdout.reconfigure(encoding='utf-8')
итог = {}
п = r'C:\sender\server\probe-dozhim.log'
if os.path.exists(п):
    итог['лог_хвост'] = io.open(п, encoding='utf-8', errors='replace').read()[-400:]
p = subprocess.run(['wmic', 'process', 'where',
                    "commandline like '%probe_dozhim%' and name like 'python%'",
                    'get', 'processid'], capture_output=True, text=True)
итог['дожим_жив'] = [x.strip() for x in (p.stdout or '').splitlines() if x.strip().isdigit()]
env = {}
for l in open(r'C:\sender\server\runner-secrets.env', encoding='utf-8'):
    if '=' in l and not l.strip().startswith('#'):
        k, v = l.split('=', 1)
        env[k.strip()] = v.strip().strip('"').strip("'")
r = subprocess.run(['curl', '-s', '-H', 'X-Drop-Token: ' + env['DROP_TOKEN'],
                    env['DROP_URL'].rstrip('/') + '/probe-zadanie.json'],
                   capture_output=True, text=True, timeout=120).stdout
try:
    задание = [str(x).lower() for x in json.loads(r or '[]')]
except Exception:  # noqa: BLE001
    задание = []
итог['в_задании'] = len(задание)
s = sqlite3.connect('file:%s?mode=ro' % r'C:/sender/sender.db', uri=True)
верд = {str(x[0]).lower() for x in s.execute('select email from addr_probe')}
наши = set()
for em, ex in s.execute("select lower(coalesce(email,'')), coalesce(extra_json,'') "
                        "from recipients where extra_json like '%Партия 935%'"):
    if not em or em in верд:
        continue
    try:
        d = json.loads(ex) if ex.strip() else {}
    except Exception:  # noqa: BLE001
        continue
    if 'Партия 935' in [str(g) for g in (d.get('gruppy') or [])]:
        наши.add(em)
s.close()
итог['наших_без_вердикта'] = len(наши)
итог['из_них_в_задании'] = len(наши & set(задание))
итог['первые_в_задании'] = задание[:5]
итог['позиция_первого_нашего'] = next(
    (i for i, a in enumerate(задание) if a in наши), None)
print(json.dumps(итог, ensure_ascii=False, indent=1)[:2000])
