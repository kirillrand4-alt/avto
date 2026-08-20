# -*- coding: utf-8 -*-
r"""Почему порог сработал на 40с, а не на 25: смотрим сам код проверки."""
import json, os, re
п = r'C:\sender\gen_provider.py'
if not os.path.exists(п):
    п = r'C:\sender\server\gen_provider.py'
t = open(п, encoding='utf-8', errors='replace').read()
d = {'файл': п}
m = re.search(r'_FIRST_TOKEN_DEADLINE\s*=.{0,160}', t, re.S)
d['объявление'] = m.group(0) if m else 'нет'
i = t.find('стрим молчит')
d['место_проверки'] = t[max(0, i-900):i+200]
print(json.dumps(d, ensure_ascii=False, indent=1)[:2800])
