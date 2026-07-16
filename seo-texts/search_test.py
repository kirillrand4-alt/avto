# -*- coding: utf-8 -*-
"""Тест внутреннего поиска: прогон фраз через /catalog/?q= и парсинг выдачи."""
import json, re, subprocess, time, urllib.parse
from concurrent.futures import ThreadPoolExecutor

UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/126.0'
phrases = json.load(open('inventory/search-test-phrases.json'))
out = open('inventory/search-results.jsonl', 'w')

CARD = re.compile(r'class="item-title"[^>]*>\s*<a[^>]*href="([^"]+)"[^>]*>\s*<span itemprop="name">([^<]+)</span>')

def probe(p):
    q = urllib.parse.quote(p['phrase'])
    url = f'https://prokompressor.ru/catalog/?q={q}'
    try:
        r = subprocess.run(['curl', '-sS', '-m', '40', '-A', UA, url],
                           capture_output=True, text=True, timeout=50)
        h = r.stdout
        cards = CARD.findall(h)
        rec = {'phrase': p['phrase'], 'source': p['source'],
               'found': len(cards), 'empty_marker': 'ничего не найдено' in h.lower(),
               'top': [{'name': n.strip(), 'url': u} for u, n in cards[:10]]}
    except Exception as ex:
        rec = {'phrase': p['phrase'], 'source': p['source'], 'error': repr(ex)[:100]}
    out.write(json.dumps(rec, ensure_ascii=False) + '\n')
    out.flush()
    time.sleep(0.3)
    return rec.get('found', -1)

with ThreadPoolExecutor(max_workers=2) as ex:
    res = list(ex.map(probe, phrases))
print(f'готово: {len(res)} фраз, пустых выдач: {sum(1 for r in res if r == 0)}, ошибок: {sum(1 for r in res if r < 0)}')
