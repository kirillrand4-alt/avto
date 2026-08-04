# -*- coding: utf-8 -*-
"""Только чтение: что делает чужой sreda_primenit.py."""
import json
out = {}
for п in (r'C:\sender\server\ops\sreda_primenit.py',
          r'C:\sender\server\ops\sreda_kratko.py'):
    try:
        out[п] = open(п, encoding='utf-8', errors='replace').read()
    except Exception as e:
        out[п] = f'ERR {e}'
print(json.dumps(out, ensure_ascii=False, indent=1))
