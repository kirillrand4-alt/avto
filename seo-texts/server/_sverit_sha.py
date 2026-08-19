# -*- coding: utf-8 -*-
"""Не менялись ли боевые файлы, пока мы правили копии."""
import hashlib
import io
import json
import sys

sys.stdout.reconfigure(encoding='utf-8')


def sha(п):
    return hashlib.sha256(io.open(п, 'rb').read()).hexdigest()[:16]


из = {}
for имя, боевой, новый in (
        ('store.py', r'C:\sender\sender\store.py', r'C:\sender\_tmp\store_novyy.py'),
        ('api/app.py', r'C:\sender\sender\api\app.py', r'C:\sender\_tmp\api_app_novyy.py')):
    из[имя] = {'боевой_sha': sha(боевой), 'новый_sha': sha(новый),
               'боевой_байт': len(io.open(боевой, 'rb').read()),
               'новый_байт': len(io.open(новый, 'rb').read())}
print(json.dumps(из, ensure_ascii=False, indent=1))
