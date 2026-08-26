# -*- coding: utf-8 -*-
"""Состояние съёма + разбор выборки checko + сколько прокси в пуле."""
import io
import json
import os
import re
import sys
import urllib.request

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
O = {}
for f in ('ozav_cards.jsonl', 'agro_apk_sample.jsonl', 'checko_sample.jsonl'):
    p = r'C:\sender\_tmp\%s' % f
    O.setdefault('файлы', {})[f] = os.path.getsize(p) if os.path.exists(p) else 0
for f in ('spr_ozav.log', 'spr_apk.log'):
    p = r'C:\sender\_tmp\%s' % f
    try:
        O.setdefault('логи', {})[f] = open(p, encoding='utf-8', errors='replace').read()[-400:]
    except Exception as e:
        O.setdefault('логи', {})[f] = str(e)[:60]
# checko выборка: примеры с сайтом и без
recs = []
p = r'C:\sender\_tmp\checko_sample.jsonl'
if os.path.exists(p):
    for ln in io.open(p, encoding='utf-8', errors='replace'):
        try:
            recs.append(json.loads(ln))
        except Exception:
            pass
O['checko_с_сайтом'] = [[r['name'][:30], r.get('sites'), int(r['rev'] / 1e6)]
                        for r in recs if r.get('sites')][:12]
O['checko_без_сайта'] = [[r['name'][:34], int(r['rev'] / 1e6), len(r.get('emails') or [])]
                         for r in recs if not r.get('sites')][:10]
O['checko_len_срез'] = sorted(set(r['len'] // 1000 for r in recs))[:12]
# прокси-пул
try:
    d = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    req = urllib.request.Request(
        os.environ.get('DROP_URL', 'https://parsercompressor.online/drop').rstrip('/')
        + '/dolphin-proxies.txt',
        headers={'X-Drop-Token': os.environ.get('DROP_TOKEN', '')})
    body = d.open(req, timeout=30).read().decode('utf-8', 'replace')
    O['прокси'] = sum(1 for l in body.splitlines()
                      if l.strip() and not l.startswith('#')
                      and re.match(r'(?:[^:@]+:[^@]*@)?[^:/]+:\d+', l.strip()))
except Exception as e:
    O['прокси'] = 'err ' + str(e)[:70]
# сводка apk
p = r'C:\sender\_tmp\agro_apk_sample.jsonl'
if os.path.exists(p):
    a = [json.loads(l) for l in io.open(p, encoding='utf-8', errors='replace') if l.strip()]
    O['apk'] = {'n': len(a), 'с_инн': sum(1 for x in a if x.get('inn')),
                'с_огрн': sum(1 for x in a if x.get('ogrn')),
                'с_внешним': sum(1 for x in a if x.get('ext')),
                'примеры_ext': [x['ext'] for x in a if x.get('ext')][:6],
                'ok200': sum(1 for x in a if x.get('st') == 200)}
# сводка ozav
p = r'C:\sender\_tmp\ozav_cards.jsonl'
if os.path.exists(p):
    z = [json.loads(l) for l in io.open(p, encoding='utf-8', errors='replace') if l.strip()]
    O['ozav'] = {'n': len(z), 'с_инн': sum(1 for x in z if x.get('inn')),
                 'с_огрн': sum(1 for x in z if x.get('ogrn')),
                 'с_сайтом': sum(1 for x in z if x.get('site')),
                 'с_почтой': sum(1 for x in z if x.get('email')),
                 'ok200': sum(1 for x in z if x.get('st') == 200)}
print(json.dumps(O, ensure_ascii=False)[:5700])
