# -*- coding: utf-8 -*-
"""Где решается retryable и что считается временной ошибкой SMTP."""
import io, json, os, re, sys
sys.stdout.reconfigure(encoding='utf-8')
из = {}
for d, _, fs in os.walk(r'C:\sender\sender'):
    if '__pycache__' in d or os.sep + 'tests' in d:
        continue
    for f in fs:
        if not f.endswith('.py'):
            continue
        t = io.open(os.path.join(d, f), encoding='utf-8', errors='replace').read()
        if 'retryable' not in t:
            continue
        строки = [(i + 1, l.strip()[:130]) for i, l in enumerate(t.splitlines())
                  if 'retryable' in l or re.search(r'\b4\d\d\b.*(врем|temp|retry)', l)]
        из[f] = строки[:12]
print(json.dumps(из, ensure_ascii=False, indent=1)[:3800])
