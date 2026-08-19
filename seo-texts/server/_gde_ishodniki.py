# -*- coding: utf-8 -*-
"""Где исходники панели: ищем package.json/vite/tsx по дискам и что в дропе."""
import json
import os
import subprocess
import sys

sys.stdout.reconfigure(encoding='utf-8')
итог = {'найдено': []}
for корень in (r'C:\sender', r'C:\seostat\drop\drop-storage', r'C:\Users\Administrator'):
    if not os.path.exists(корень):
        continue
    гл = 0
    for d, ds, fs in os.walk(корень):
        ds[:] = [x for x in ds if x not in ('node_modules', '.git', 'dist', '_ops')]
        гл += 1
        if гл > 6000:
            break
        if 'package.json' in fs or 'vite.config.ts' in fs or 'vite.config.js' in fs:
            итог['найдено'].append({'путь': d, 'файлы': sorted(
                x for x in fs if x.endswith(('.json', '.ts', '.js')))[:6]})
        if any(x.endswith(('.tsx', '.vue')) for x in fs):
            итог.setdefault('с_компонентами', []).append(d)
итог['с_компонентами'] = (итог.get('с_компонентами') or [])[:10]
# на дропе
env = {}
for l in open(r'C:\sender\server\runner-secrets.env', encoding='utf-8'):
    if '=' in l and not l.strip().startswith('#'):
        k, v = l.split('=', 1)
        env[k.strip()] = v.strip().strip('"').strip("'")
r = subprocess.run(['curl', '-s', '-H', 'X-Drop-Token: ' + env['DROP_TOKEN'],
                    env['DROP_URL'].rstrip('/') + '/list'],
                   capture_output=True, text=True, timeout=180).stdout
try:
    имена = [f if isinstance(f, str) else f.get('name', '') for f in json.loads(r)]
except Exception:  # noqa: BLE001
    имена = []
итог['похоже_на_фронт_в_дропе'] = [x for x in имена if any(
    k in x.lower() for k in ('web', 'front', 'panel-src', 'src.zip', 'ui', '.tsx'))][:12]
print(json.dumps(итог, ensure_ascii=False, indent=1)[:3000])
