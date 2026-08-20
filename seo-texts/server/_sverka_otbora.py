# -*- coding: utf-8 -*-
r"""Что на сервере в отборе компаний и как выглядят полностью пустые паспорта."""
import json
import sqlite3

d = {}
п = r'C:\sender\server\site_facts.py'
with open(п, encoding='utf-8') as f:
    строки = f.readlines()
for i, s in enumerate(строки):
    if 'istochnik = spisok if spisok is not None' in s or 'komp = [k for k' in s:
        d.setdefault('отбор', []).append('%d: %s' % (i + 1, s.rstrip()[:120]))
d['FORMAT_на_сервере'] = [s.strip() for s in строки if s.startswith('FORMAT')][:1]

c = sqlite3.connect('file:C:/sender/enrich.db?mode=ro', uri=True, timeout=60)
c.row_factory = sqlite3.Row
пустые = []
for r in c.execute("select inn, coalesce(site,'') site, coalesce(note,'') note, "
                   'facts_json f from site_facts where coalesce(format,0)>=2 '
                   "and coalesce(facts_json,'')<>'' limit 4000"):
    try:
        j = json.loads(r['f'])
    except Exception:  # noqa: BLE001
        continue
    if any(j.get(k) for k in j if k not in ('уверенность', 'источники')):
        continue
    пустые.append({'инн': str(r['inn']), 'сайт': r['site'][:48],
                   'уверенность': j.get('уверенность'),
                   'источников': len(j.get('источники') or []),
                   'ключей': len(j)})
    if len(пустые) >= 8:
        break
d['совсем_пустые_паспорта'] = пустые
c.close()
print(json.dumps(d, ensure_ascii=False, indent=1))
