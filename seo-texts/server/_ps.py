# -*- coding: utf-8 -*-
import json, re, os
п = r'C:\sender\sender\probe_sync.py'
if not os.path.exists(п):
    print(json.dumps({'нет файла': п})); raise SystemExit
t = open(п, encoding='utf-8', errors='replace').read()
d = {'байт': len(t), 'функции': re.findall(r'\n    def (\w+)', t)}
i = t.find('def опубликовать')
d['опубликовать'] = t[i:i+2200] if i > 0 else 'не найдено'
i2 = t.find('def _kogo_probovat')
if i2 < 0:
    i2 = t.find('def кого')
d['кого_выбираем'] = t[i2:i2+1800] if i2 > 0 else ''
print(json.dumps(d, ensure_ascii=False, indent=1)[:4000])
