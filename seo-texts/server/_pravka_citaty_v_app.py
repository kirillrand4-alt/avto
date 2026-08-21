# -*- coding: utf-8 -*-
r"""Передать в страницу лида третью чистилку — срезание цитаты."""
import json
import re

П = r'C:\sender\sender\api\app.py'
with open(П, encoding='utf-8') as f:
    т = f.read()
d = {}
куски = re.findall(r'.{0,200}LS\.bez_podpisi.{0,200}', т, re.S)
d['было'] = [к.replace('\n', ' | ')[:300] for к in куски]
было = '(LS.bez_podpisi, LS.bez_adresov)'
стало = '(LS.bez_podpisi, LS.bez_adresov, LS.bez_citaty)'
if стало in т:
    d['итог'] = 'уже стояло'
elif было in т:
    т = т.replace(было, стало)
    with open(П, 'w', encoding='utf-8', newline='') as f:
        f.write(т)
    d['итог'] = 'заменено'
else:
    d['итог'] = 'НЕ НАШЁЛ кортеж чистилок'
print(json.dumps(d, ensure_ascii=False, indent=1)[:1800])
