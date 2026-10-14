# -*- coding: utf-8 -*-
r"""fixX: привязан ли вход панели Meyer к домену (cookie domain/secure, проверка Origin/Referer/Host, жёсткие адреса). Только чтение.

    python3 zapusk_na_servere.py fixX_vhod_razvedka.py
"""
import io
import os
import re

for kor, _, fajly in [(r'C:\centro2\app\api', 0, os.listdir(r'C:\centro2\app\api')), (r'C:\centro2\app\services', 0, os.listdir(r'C:\centro2\app\services')), (r'C:\centro2\app', 0, ['obzvon.py', 'web.py', 'config.py'])]:
    for f in fajly:
        if not f.endswith(('.py', '.html', '.js')):
            continue
        p = os.path.join(kor, f)
        for i, s in enumerate(io.open(p, encoding='utf-8', errors='replace').read().splitlines(), 1):
            if re.search(r'set_cookie|domain\s*=|parsercompressor|sort-inspection|[Oo]rigin|[Rr]eferer|request\.url\.hostname|headers\.get\(.host|TrustedHost|allowed_hosts|samesite|secure\s*=', s):
                print('%s:%d: %s' % (p.replace(r'C:\centro2\app', ''), i, s.strip()[:180]))
for f in (r'C:\centro2\.env', r'C:\centro2\zapusk.py'):
    if os.path.exists(f):
        for i, s in enumerate(io.open(f, encoding='utf-8', errors='replace').read().splitlines(), 1):
            if re.search(r'(?i)host|domain|cookie|origin|url', s) and not re.search(r'(?i)token|secret|password|key', s):
                print('%s:%d: %s' % (f, i, s.strip()[:160]))
