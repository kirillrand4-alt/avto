# -*- coding: utf-8 -*-
r"""По чему сортируется очередь подтверждения: ищем «score» в confirm.py."""
import json
import re

п = r'C:\sender\sender\confirm.py'
with open(п, encoding='utf-8', errors='replace') as f:
    строки = f.read().splitlines()
инт = []
for i, s in enumerate(строки):
    if re.search(r'score|order|sort|ранг|приоритет|priority', s, re.I):
        инт.append('%d: %s' % (i + 1, s.strip()[:140]))
print(json.dumps({'confirm.py': инт[:40]}, ensure_ascii=False, indent=1)[:3200])
