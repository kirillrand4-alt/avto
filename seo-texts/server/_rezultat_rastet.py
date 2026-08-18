# -*- coding: utf-8 -*-
"""Растёт ли probe-rezultat.jsonl на дропе и сколько там НАШИХ адресов."""
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
p = subprocess.run(['curl', '-s', '-H', 'X-Drop-Token: ' + tok,
                    url + '/probe-rezultat.jsonl'],
                   capture_output=True, text=True, timeout=180)
текст = p.stdout or ''
строки = [l for l in текст.splitlines() if l.strip()]
задание = subprocess.run(['curl', '-s', '-H', 'X-Drop-Token: ' + tok,
                          url + '/probe-zadanie.json'],
                         capture_output=True, text=True, timeout=120).stdout
try:
    наши = set(json.loads(задание))
except Exception:  # noqa: BLE001
    наши = set()
готовы, времена = 0, []
for l in строки:
    try:
        d = json.loads(l)
    except Exception:  # noqa: BLE001
        continue
    if d.get('email') in наши:
        готовы += 1
    if d.get('ts'):
        времена.append(d['ts'])
времена.sort()
print(json.dumps({
    'байт': len(текст), 'строк': len(строки),
    'в_задании': len(наши), 'из_задания_проверено': готовы,
    'последний_ts_в_файле': времена[-1] if времена else '',
    'сейчас_utc': time.strftime('%Y-%m-%dT%H:%M:%S', time.gmtime()),
    'сейчас_местное': time.strftime('%Y-%m-%d %H:%M')}, ensure_ascii=False))
