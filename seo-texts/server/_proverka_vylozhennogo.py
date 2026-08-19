# -*- coding: utf-8 -*-
"""Что реально отдаёт панель после выкладки: индекс, бандл, наши строки."""
import io
import json
import os
import re
import subprocess
import sys

sys.stdout.reconfigure(encoding='utf-8')
DIST = r'C:\sender\web\dist'
html = io.open(os.path.join(DIST, 'index.html'), encoding='utf-8',
               errors='replace').read()
m = re.search(r'assets/(index-[\w-]+\.js)', html)
итог = {'index_ссылается': m.group(1) if m else '—'}
if m:
    п = os.path.join(DIST, 'assets', m.group(1))
    итог['бандл_есть'] = os.path.exists(п)
    if os.path.exists(п):
        t = io.open(п, encoding='utf-8', errors='replace').read()
        итог['есть_перевести'] = '→ перевести' in t or 'перевести' in t
        итог['крестика_нет'] = 'убрать из ленты' not in t
        итог['есть_подписи'] = all(x in t for x in
                                   ('квалифицирован', 'передан в Bitrix', 'позвонил'))
p = subprocess.run(['curl', '-s', '-o', 'NUL', '-w', '%{http_code}',
                    'http://127.0.0.1:8091/'], capture_output=True, text=True, timeout=60)
итог['панель_отвечает'] = (p.stdout or '').strip()
print(json.dumps(итог, ensure_ascii=False, indent=1))
