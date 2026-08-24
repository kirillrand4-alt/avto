# -*- coding: utf-8 -*-
r"""Что определяет порядок писем: влияет ли роль адреса на очерёдность."""
import json
import os
import re

d = {}
п = r'C:\sender\sender\api\app.py'
with open(п, encoding='utf-8', errors='replace') as f:
    т = f.read()
м = re.search(r'@app\.get\("/confirm/queue"\).{0,12000}?(?=@app\.)', т, re.S)
кусок = м.group(0) if м else ''
d['сортировка_в_очереди'] = [s.strip()[:130] for s in кусок.splitlines()
                             if re.search(r'sort|order|score|ранг|rank', s)][:14]
# как выбирается адрес компании при генерации
for файл in (r'C:\sender\sender\ai_letter.py', r'C:\sender\server\dogruz_935.py',
             r'C:\sender\sender\cadence.py'):
    if not os.path.exists(файл):
        continue
    with open(файл, encoding='utf-8', errors='replace') as f:
        тт = f.read()
    строки = [s.strip()[:120] for s in тт.splitlines()
              if re.search(r'_ранг|role_rank|ROLE_RANK|order by|sorted\(', s)]
    if строки:
        d[os.path.basename(файл)] = строки[:10]
print(json.dumps(d, ensure_ascii=False, indent=1)[:3000])
