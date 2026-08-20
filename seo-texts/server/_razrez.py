# -*- coding: utf-8 -*-
import json, re
t = open(r'C:\sender\gen_provider.py', encoding='utf-8', errors='replace').read()
i = t.find('ГРАНИЦЫ РАЗРЕЗА ПРОМПТА')
d = {'кусок': t[i-100:i+1800]}
d['cache_control_встречается'] = t.count('cache_control')
m = re.findall(r'.{160}cache_control.{200}', t, re.S)
d['места'] = m[:3]
print(json.dumps(d, ensure_ascii=False, indent=1)[:3200])
