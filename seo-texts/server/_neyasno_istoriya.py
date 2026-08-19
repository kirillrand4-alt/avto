# -*- coding: utf-8 -*-
"""Судьба 166 выведенных в стоп-листе + во что превращались «неясно» при повторах.

История лежит в накопленном probe-rezultat.jsonl: работник ДОПИСЫВАЕТ строки, и
у адреса, проверенного не раз, там несколько записей. По ним видно, во что
превращается «неясно» при повторной пробе — а это и есть вопрос владельца.
"""
import json
import subprocess
import sqlite3
import sys

sys.stdout.reconfigure(encoding='utf-8')
итог = {}
s = sqlite3.connect('file:%s?mode=ro' % r'C:/sender/sender.db', uri=True)
стоп = {str(r[0]).lower() for r in s.execute(
    "select value from suppression where scope='email'")}
выведенные = set()
for em, ex in s.execute("select lower(coalesce(email,'')), coalesce(extra_json,'') "
                        "from recipients where extra_json like '%проверка VPS%'"):
    if em:
        выведенные.add(em)
итог['выведенных'] = len(выведенные)
итог['из_них_в_стоп-листе'] = len(выведенные & стоп)
итог['не_в_стоп-листе'] = len(выведенные - стоп)
неясные = {str(r[0]).lower() for r in s.execute(
    "select email from addr_probe where verdict='неясно'")}
итог['сейчас_неясно_всего'] = len(неясные)
s.close()

env = {}
for l in open(r'C:\sender\server\runner-secrets.env', encoding='utf-8'):
    if '=' in l and not l.strip().startswith('#'):
        k, v = l.split('=', 1)
        env[k.strip()] = v.strip().strip('"').strip("'")
текст = subprocess.run(['curl', '-s', '-H', 'X-Drop-Token: ' + env['DROP_TOKEN'],
                        env['DROP_URL'].rstrip('/') + '/probe-rezultat.jsonl'],
                       capture_output=True, text=True, timeout=240).stdout or ''
история = {}
for л in текст.splitlines():
    try:
        d = json.loads(л)
    except Exception:  # noqa: BLE001
        continue
    a = str(d.get('email') or '').lower()
    if a:
        история.setdefault(a, []).append((d.get('ts') or '', d.get('verdict') or ''))
итог['адресов_в_журнале'] = len(история)
повторные = {a: v for a, v in история.items() if len(v) > 1}
итог['проверялись_не_раз'] = len(повторные)
переходы = {}
for a, v in повторные.items():
    v.sort()
    if v[0][1] == 'неясно':
        переходы[v[-1][1]] = переходы.get(v[-1][1], 0) + 1
итог['было_неясно_стало'] = dict(sorted(переходы.items(), key=lambda kv: -kv[1]))
итог['примеры_ответов_неясно'] = []
for л in текст.splitlines():
    try:
        d = json.loads(л)
    except Exception:  # noqa: BLE001
        continue
    if d.get('verdict') == 'неясно' and len(итог['примеры_ответов_неясно']) < 6:
        итог['примеры_ответов_неясно'].append(
            {'адрес': d.get('email'), 'код': d.get('code'),
             'ответ': str(d.get('answer') or '')[:90]})
print(json.dumps(итог, ensure_ascii=False, indent=1))
