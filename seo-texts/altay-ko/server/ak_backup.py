# -*- coding: utf-8 -*-
"""Копия AK-BAZA.sqlite и jsonl-потоков на дроп (durable). argv: [имена файлов...] по умолчанию база."""
import os, sys, urllib.request, time, glob
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
AK = r'C:\sender\_ops\ak'
names = sys.argv[1:] or ['AK-BAZA.sqlite']
if names == ['ALL']:
    names = ['AK-BAZA.sqlite'] + [os.path.basename(f) for f in glob.glob(os.path.join(AK, '*.jsonl'))]
for n in names:
    p = os.path.join(AK, n)
    if not os.path.exists(p): print('нет', n); continue
    data = open(p, 'rb').read(); t = time.time()
    req = urllib.request.Request(os.environ['DROP_URL'].rstrip('/') + '/AK-' + n.replace('AK-', ''), data=data, method='PUT', headers={'X-Drop-Token': os.environ['DROP_TOKEN'], 'Content-Type': 'application/octet-stream'})
    try:
        r = urllib.request.urlopen(req, timeout=600); print(n, r.status, len(data) // 1024, 'КБ', round(time.time() - t, 1), 'с')
    except Exception as e: print(n, 'ERR', repr(e)[:120])
