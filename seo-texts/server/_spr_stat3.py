# -*- coding: utf-8 -*-
"""Прогресс + полнота каталога o-zavodah (индексная страница против sitemap)."""
import io
import json
import os
import re
import sys
import urllib.request

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/126.0 Safari/537.36 (+prokompressor.ru research)')
O = {}
try:
    req = urllib.request.Request('https://o-zavodah.ru/zavody/', headers={
        'User-Agent': UA, 'Cookie': 'beget=begetok'})
    h = urllib.request.urlopen(req, timeout=40).read().decode('utf-8', 'replace')
    O['индекс_zavody_ссылок'] = len(set(re.findall(r'href="(/zavody/[^"]+/)"', h)))
    t = re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', h))
    O['индекс_фраза'] = re.findall(r'[^.]{0,80}(?:завод|предприят)[^.]{0,60}', t)[:2]
except Exception as e:
    O['индекс_zavody_ссылок'] = str(e)[:60]
for f, k in (('ozav_cards.jsonl', 'ozav'), ('agro_cards.jsonl', 'agro'),
             ('agro_apk_sample.jsonl', 'apk')):
    p = r'C:\sender\_tmp\%s' % f
    n = 0
    if os.path.exists(p):
        n = sum(1 for _ in io.open(p, encoding='utf-8', errors='replace'))
    O[k + '_строк'] = n
for f in ('spr_ozav.log', 'spr_agro.log'):
    try:
        O.setdefault('логи', {})[f] = open(r'C:\sender\_tmp\%s' % f,
                                           encoding='utf-8', errors='replace').read()[-90:]
    except Exception as e:
        O.setdefault('логи', {})[f] = str(e)[:40]
print(json.dumps(O, ensure_ascii=False)[:2500])
