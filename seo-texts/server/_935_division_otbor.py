# -*- coding: utf-8 -*-
"""Как ai_quota набирает получателей в кампанию и откуда берётся division."""
import io
import json
import re
import sys

sys.stdout.reconfigure(encoding='utf-8')
итог = {}
t = io.open(r'C:\sender\sender\company_card.py', encoding='utf-8',
            errors='replace').read()
m = re.search(r'DIVISION_BY_BASE\s*=.*?\n\n', t, re.S)
итог['DIVISION_BY_BASE'] = m.group(0)[:900] if m else ''
m = re.search(r'def campaign_division.*?(?=\ndef |\nclass )', t, re.S)
итог['campaign_division'] = m.group(0)[:1500] if m else ''
import os

for файл in ('ai_letter.py', 'panel.py', 'web.py', 'app.py'):
    p = r'C:\sender\sender\%s' % файл
    if not os.path.exists(p):
        continue
    t = io.open(p, encoding='utf-8', errors='replace').read()
    for имя in ('ai_quota', '_kandidaty', 'pick_recipients', '_recipient_query'):
        m = re.search(r'def [\w_]*%s[\w_]*\(.*?(?=\n    def |\ndef |\nclass )'
                      % имя, t, re.S)
        if m:
            итог['%s:%s' % (файл, имя)] = m.group(0)[:1800]
print(json.dumps(итог, ensure_ascii=False, indent=1)[:5600])
