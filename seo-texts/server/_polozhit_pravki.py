# -*- coding: utf-8 -*-
"""Положить изменённые файлы фронта в папку правок на сервере."""
import json
import os
import shutil
import sys

sys.stdout.reconfigure(encoding='utf-8')
КУДА = r'C:\sender\_tmp\web-pravki'
os.makedirs(os.path.join(КУДА, 'screens'), exist_ok=True)
os.makedirs(os.path.join(КУДА, 'api'), exist_ok=True)
положено = []
for имя, куда in (('Leads.tsx', 'screens'), ('LeadCard.tsx', 'screens'),
                  ('client.ts', 'api')):
    ист = os.path.join(r'C:\sender\_tmp', имя)
    if os.path.exists(ист):
        shutil.copy(ист, os.path.join(КУДА, куда, имя))
        положено.append('%s/%s' % (куда, имя))
print(json.dumps({'положено': положено}, ensure_ascii=False))
