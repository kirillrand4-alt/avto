# -*- coding: utf-8 -*-
r"""Как панель пускает к API: ищем схему аутентификации в app.py и конфиге."""
import json
import os
import re

d = {}
п = r'C:\sender\sender\api\app.py'
with open(п, encoding='utf-8', errors='replace') as f:
    строки = f.readlines()
инт = []
for i, s in enumerate(строки):
    if re.search(r'def principal|Principal|api_key|APIKey|Header\(|Cookie\(|'
                 r'token|basic|Depends\(principal\)', s):
        if len(инт) < 40:
            инт.append('%d: %s' % (i + 1, s.strip()[:120]))
d['app.py'] = инт[:40]
try:
    with open(r'C:\sender\sender.yaml', encoding='utf-8') as f:
        текст = f.read()
    d['yaml_строки_про_доступ'] = [s.strip()[:110] for s in текст.splitlines()
                                   if re.search(r'token|pass|user|auth|key', s, re.I)][:12]
except Exception as e:  # noqa: BLE001
    d['yaml'] = str(e)[:100]
for имя in ('PANEL_TOKEN', 'API_TOKEN', 'SENDER_TOKEN'):
    if os.environ.get(имя):
        d.setdefault('env', []).append(имя)
print(json.dumps(d, ensure_ascii=False, indent=1)[:3600])
