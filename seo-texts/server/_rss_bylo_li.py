# -*- coding: utf-8 -*-
"""Участвовала ли база RSS-лент в этом прогоне: каталог, доноры, что пришло."""
import io
import json
import os
import sqlite3
import urllib.request

DIR = r'C:\sender\server'
o = {}

# 1. Каталог региональных лент (его читает коллектор regional).
try:
    url = os.environ.get('DROP_URL', '').rstrip('/') + '/news-sources.json'
    req = urllib.request.Request(url, headers={'X-Drop-Token': os.environ.get('DROP_TOKEN', '')})
    d = json.loads(urllib.request.urlopen(req, timeout=30).read())
    feeds = d.get('feeds', [])
    tiers = {}
    for ф in feeds:
        t = (ф or {}).get('tier') if isinstance(ф, dict) else '?'
        tiers[str(t)] = tiers.get(str(t), 0) + 1
    o['каталог_с_дропа'] = {'лент': len(feeds), 'по_тирам': tiers}
except Exception as e:
    o['каталог_с_дропа'] = 'ОШИБКА: %r' % (e,)

print('===ИТОГ===')
print(json.dumps(o, ensure_ascii=False, indent=1, default=str))
