# -*- coding: utf-8 -*-
"""Что лежит на дропе по проверке: забрал ли работник задание и есть ли ответы."""
import json
import subprocess
import sys

sys.stdout.reconfigure(encoding='utf-8')
env = {}
for l in open(r'C:\sender\server\runner-secrets.env', encoding='utf-8'):
    if '=' in l and not l.strip().startswith('#'):
        k, v = l.split('=', 1)
        env[k.strip()] = v.strip().strip('"').strip("'")
url, tok = env['DROP_URL'].rstrip('/'), env['DROP_TOKEN']


def дроп(путь):
    p = subprocess.run(['curl', '-s', '-H', 'X-Drop-Token: ' + tok, url + путь],
                       capture_output=True, text=True, timeout=120)
    return p.stdout or ''


итог = {}
сырой = дроп('/list')
try:
    файлы = json.loads(сырой)
except Exception:  # noqa: BLE001
    файлы = сырой[:300]
if isinstance(файлы, list):
    имена = [f if isinstance(f, str) else (f.get('name') or f.get('file') or str(f))
             for f in файлы]
    vjob = sorted(f for f in имена if f.startswith('vjob'))
    итог['vjob_всего'] = len(vjob)
    итог['vjob_самый_старый'] = vjob[0] if vjob else ''
    итог['vjob_самый_новый'] = vjob[-1] if vjob else ''
    import time as _t
    def _ts(f):
        ч = f.split('-')
        return int(ч[1]) if len(ч) > 1 and ч[1].isdigit() else 0
    if vjob:
        итог['vjob_даты'] = [_t.strftime('%Y-%m-%d %H:%M', _t.localtime(_ts(vjob[0]))),
                             _t.strftime('%Y-%m-%d %H:%M', _t.localtime(_ts(vjob[-1])))]
        итог['сейчас'] = _t.strftime('%Y-%m-%d %H:%M')
    итог['probe_файлы'] = [f for f in имена if f.startswith('probe-')]
    итог['всего_файлов'] = len(имена)
else:
    итог['список_сырой'] = файлы
з = дроп('/probe-zadanie.json')
try:
    сп = json.loads(з)
    итог['в_задании'] = len(сп) if isinstance(сп, list) else 'не список'
    итог['первые'] = сп[:3] if isinstance(сп, list) else str(сп)[:120]
except Exception:  # noqa: BLE001
    итог['задание'] = з[:150]
р = дроп('/probe-rezultat.jsonl')
итог['результат_байт'] = len(р)
итог['результат_хвост'] = р[-300:] if р else ''
итог.pop('список_сырой', None)
print(json.dumps(итог, ensure_ascii=False, indent=1)[:2200])
