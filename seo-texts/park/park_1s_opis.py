# -*- coding: utf-8 -*-
"""Опись серверной песочницы: какие операции лежат в _ops и какие накопители растут."""
import os, json, time
B = r'C:\sender'
o = {}
try:
    o['_ops_py'] = sorted(x for x in os.listdir(os.path.join(B, '_ops')) if x.endswith('.py'))
except Exception as e:
    o['_ops_err'] = str(e)

def opis(pred):
    return [[x, os.path.getsize(os.path.join(B, x)),
             time.strftime('%d.%m %H:%M', time.gmtime(os.path.getmtime(os.path.join(B, x))))]
            for x in sorted(os.listdir(B)) if pred(x)]

o['jsonl'] = opis(lambda x: x.endswith('.jsonl'))
o['db'] = opis(lambda x: x.endswith('.db'))
print(json.dumps(o, ensure_ascii=False, indent=1))
