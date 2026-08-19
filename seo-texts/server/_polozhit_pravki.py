# -*- coding: utf-8 -*-
"""Положить изменённый Leads.tsx в папку правок на сервере."""
import os, shutil, sys, json
sys.stdout.reconfigure(encoding='utf-8')
os.makedirs(r'C:\sender\_tmp\web-pravki', exist_ok=True)
shutil.copy(r'C:\sender\_tmp\Leads.tsx', r'C:\sender\_tmp\web-pravki\Leads.tsx')
print(json.dumps({'положено': 'Leads.tsx'}, ensure_ascii=False))
