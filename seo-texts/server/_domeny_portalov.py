# -*- coding: utf-8 -*-
"""Какие домены правило считает «общим порталом» — глазами, прежде чем метить."""
import json
import sqlite3
import sys

sys.stdout.reconfigure(encoding='utf-8')
c = sqlite3.connect('file:%s?mode=ro' % r'C:/sender/enrich.db', uri=True)
по_домену = {}
for inn, email in c.execute("select inn, email from emails where coalesce(email,'')<>''"):
    д = (str(email).split('@')[-1] or '').lower().strip('.')
    if д:
        по_домену.setdefault(д, set()).add(str(inn))
c.close()
топ = sorted(((len(v), k) for k, v in по_домену.items()), reverse=True)[:25]
print(json.dumps({'доменов_всего': len(по_домену),
                  'топ_по_числу_юрлиц': [{'домен': d, 'юрлиц': n} for n, d in топ]},
                 ensure_ascii=False, indent=1)[:2200])
