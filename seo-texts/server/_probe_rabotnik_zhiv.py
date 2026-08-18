# -*- coding: utf-8 -*-
"""Признаки жизни работника: файлы-отметки на дропе и когда их трогали."""
import json
import subprocess
import sys
import time

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
итог['probe-claude2.txt'] = дроп('/probe-claude2.txt')[:400]
сырой = дроп('/list')
try:
    файлы = json.loads(сырой)
except Exception:  # noqa: BLE001
    файлы = []
имена = [f if isinstance(f, str) else (f.get('name') or str(f)) for f in файлы]
# всё, что похоже на отметку работника/раннера VPS
итог['похожие_на_отметки'] = sorted(
    f for f in имена if any(k in f.lower() for k in
                            ('vres', 'vstatus', 'heartbeat', 'zhiv', 'alive',
                             'worker', 'rabotnik', 'vps')))[:12]
# ответы раннера на задачи: обычно vres-<id>
итог['vres_всего'] = len([f for f in имена if f.startswith('vres')])
vres = sorted(f for f in имена if f.startswith('vres'))
if vres:
    def _ts(f):
        ч = f.split('-')
        return int(ч[1]) if len(ч) > 1 and ч[1].isdigit() else 0
    итог['vres_последний'] = vres[-1]
    итог['vres_последний_время'] = time.strftime(
        '%Y-%m-%d %H:%M', time.localtime(_ts(vres[-1])))
итог['сейчас'] = time.strftime('%Y-%m-%d %H:%M')
print(json.dumps(итог, ensure_ascii=False, indent=1)[:2200])
