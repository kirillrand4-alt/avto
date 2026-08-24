# -*- coding: utf-8 -*-
r"""Как устроена лента лидов: фильтры на фронте и параметры ручки."""
import json
import os
import re

d = {}
для = r'C:\sender\_tmp\web-pravki\screens\Leads.tsx'
если = для if os.path.exists(для) else r'C:\sender\_tmp\web-src-iz-mapy\screens\Leads.tsx'
d['файл'] = если
строки = open(если, encoding='utf-8', errors='replace').read().splitlines()
d['всего_строк'] = len(строки)
d['фильтры'] = ['%d: %s' % (i + 1, s.strip()[:120]) for i, s in enumerate(строки)
                if re.search(r'status|статус|filter|фильтр|chip|napravlenie', s, re.I)][:30]
п = r'C:\sender\sender\api\app.py'
т = open(п, encoding='utf-8', errors='replace').read()
м = re.search(r'@app\.get\("/leads"\).{0,2500}?(?=@app\.)', т, re.S)
d['ручка_leads'] = [s.strip()[:130] for s in (м.group(0) if м else '').splitlines()][:26]
print(json.dumps(d, ensure_ascii=False, indent=1)[:3600])
