# -*- coding: utf-8 -*-
"""Панель после перезапуска: жива ли, поднялись ли новые ручки, нет ли ошибок."""
import json
import os
import subprocess
import sys
import time

sys.stdout.reconfigure(encoding='utf-8')
итог = {}
p = subprocess.run(['powershell', '-NoProfile', '-Command',
                    "(Get-Service SenderPanel).Status"],
                   capture_output=True, text=True, timeout=120)
итог['служба'] = (p.stdout or p.stderr or '').strip()[:40]
# ручки
for путь, ожидание in (('/', 'страница'), ('/api/openapi.json', 'схема API')):
    r = subprocess.run(['curl', '-s', '-o', 'NUL', '-w', '%{http_code}',
                        'http://127.0.0.1:8091' + путь],
                       capture_output=True, text=True, timeout=60)
    итог[ожидание] = (r.stdout or '').strip()
# есть ли в схеме наша ручка вложений и поле attachments
r = subprocess.run(['curl', '-s', 'http://127.0.0.1:8091/api/openapi.json'],
                   capture_output=True, text=True, timeout=90)
try:
    схема = json.loads(r.stdout or '{}')
    пути = list((схема.get('paths') or {}).keys())
    итог['ручка_/vlozheniya'] = '/vlozheniya' in пути
    тело = ((схема.get('components') or {}).get('schemas') or {}).get('LeadReplyBody') or {}
    итог['поле_attachments'] = 'attachments' in (тело.get('properties') or {})
    итог['всего_ручек'] = len(пути)
except Exception as e:  # noqa: BLE001
    итог['схема_ошибка'] = str(e)[:120]
# хвост журнала службы
for лог in (r'C:\sender\panel.log', r'C:\sender\logs\panel.log',
            r'C:\sender\sender.log'):
    if os.path.exists(лог):
        import io
        итог['лог'] = io.open(лог, encoding='utf-8', errors='replace').read()[-700:]
        break
print(json.dumps(итог, ensure_ascii=False, indent=1)[:2500])
