# -*- coding: utf-8 -*-
"""Баланс XMLRiver и что он исторически дал в новостном скане."""
import io
import json
import os
import sys
import urllib.request

sys.path.insert(0, r'C:\sender\server')
os.chdir(r'C:\sender\server')
o = {}
U = os.environ.get('XMLRIVER_USER', '')
K = os.environ.get('XMLRIVER_KEY', '')
o['ключ_есть'] = bool(U and K)
for имя, url in (('google', 'http://xmlriver.com/api/get_balance/?user=%s&key=%s'),
                 ('yandex', 'http://xmlriver.com/api/get_balance/?user=%s&key=%s')):
    try:
        with urllib.request.urlopen(url % (U, K), timeout=40) as r:
            o['баланс_' + имя] = r.read(200).decode('utf-8', 'replace').strip()
        break
    except Exception as e:
        o['баланс_' + имя] = repr(e)[:90]

# Сколько событий исторически дал xmlriver и сколько из них с ИНН.
кол, с_инн, свежие = {}, {}, {}
with io.open(r'C:\sender\server\news_stream.jsonl', encoding='utf-8', errors='replace') as f:
    for s in f:
        if '"collector"' not in s:
            continue
        try:
            d = json.loads(s)
        except Exception:
            continue
        k = d.get('collector') or '?'
        кол[k] = кол.get(k, 0) + 1
        if str(d.get('inn') or '').strip():
            с_инн[k] = с_инн.get(k, 0) + 1
o['событий_по_коллекторам'] = кол
o['с_ИНН_по_коллекторам'] = с_инн
print('===ИТОГ===')
print(json.dumps(o, ensure_ascii=False, indent=1))
