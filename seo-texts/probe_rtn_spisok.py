# -*- coding: utf-8 -*-
"""Список территориальных управлений: страница структуры их не содержит, ищем настоящую.

ПОВОД. `/about/structure/` отдала 200 и ровно три поддомена — en, m, www, то есть собственные
служебные. Ноль территориальных управлений на странице структуры это не ответ, а признак, что
взята не та страница. Пробую известные разделы и печатаю, сколько поддоменов дал каждый, —
победит тот, где их десятки.
"""
import json
import re
import urllib.request

UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36')
PUTI = ['/about/structure/terr/', '/about/territorial/', '/territorial/',
        '/about/structure/territorial/', '/sitemap/', '/about/', '/']
naydeno = {}
vse = set()
for p in PUTI:
    u = 'https://www.gosnadzor.ru' + p
    try:
        req = urllib.request.Request(u, headers={'User-Agent': UA})
        with urllib.request.urlopen(req, timeout=40) as r:
            h = r.read().decode('utf-8', 'replace')
        pd = set(re.findall(r'https?://([a-z0-9\-]+)\.gosnadzor\.ru', h)) - {'en', 'm', 'www'}
        naydeno[p] = len(pd)
        vse |= pd
    except Exception as e:  # noqa: BLE001
        naydeno[p] = f'{type(e).__name__}'
print(json.dumps({'по_страницам': naydeno, 'всего_разных': len(vse),
                  'управления': sorted(vse)}, ensure_ascii=False))
