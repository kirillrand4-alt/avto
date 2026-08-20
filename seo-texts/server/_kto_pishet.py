# -*- coding: utf-8 -*-
import json, os, re
d = {}
for корень, _, файлы in os.walk(r'C:\sender\sender'):
    for f in файлы:
        if not f.endswith('.py'):
            continue
        p = os.path.join(корень, f)
        t = open(p, encoding='utf-8', errors='replace').read()
        if 'копия письма в очереди' in t or 'новый адрес:' in t:
            for m in re.finditer(r'.{220}(копия письма в очереди|новый адрес:).{160}', t, re.S):
                d.setdefault(p, []).append(m.group(0))
print(json.dumps({k: v[:2] for k, v in d.items()}, ensure_ascii=False, indent=1)[:2600])
