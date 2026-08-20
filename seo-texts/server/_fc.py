# -*- coding: utf-8 -*-
import json
t = open(r'C:\sender\server\fakty_cikl.py', encoding='utf-8', errors='replace').read()
print(json.dumps({'байт': len(t), 'начало': t[:1800]}, ensure_ascii=False, indent=1)[:2400])
