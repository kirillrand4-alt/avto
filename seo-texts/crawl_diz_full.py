# -*- coding: utf-8 -*-
import re, html as H, json, subprocess, sys
from concurrent.futures import ThreadPoolExecutor

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126.0 Safari/537.36"
pages = json.load(open('diz-brands-pages.json'))
jobs = []
for r in pages:
    for p in range(1, (r.get('max_pagen') or 1) + 1):
        jobs.append((r['slug'], r['url'] + (f'?PAGEN_1={p}' if p > 1 else '')))

def work(job):
    slug, u = job
    try:
        res = subprocess.run(['curl','-sS','--max-time','40','-A',UA,u], capture_output=True, text=True, timeout=50)
        cards = re.findall(r'itemprop="url"[^>]*>\s*<span itemprop="name">([^<]+)</span>', res.stdout)
        return slug, [H.unescape(c.strip()) for c in cards]
    except Exception:
        return slug, []

names = {}
with ThreadPoolExecutor(max_workers=6) as ex:
    for slug, cards in ex.map(work, jobs):
        names.setdefault(slug, [])
        names[slug] += cards
for s in names: names[s] = sorted(set(names[s]))
json.dump(names, open('diz-brands-models.json','w'), ensure_ascii=False, indent=1)
for s, lst in sorted(names.items()):
    print(f'{s:<24} {len(lst)} моделей | {lst[0][:60] if lst else "-"}', file=sys.stderr)
