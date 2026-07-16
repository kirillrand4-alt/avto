# -*- coding: utf-8 -*-
"""Проверка наличия наших текстов на всех 759 живых страницах prokompressor.ru."""
import glob, json, subprocess, sys
from concurrent.futures import ThreadPoolExecutor

pages = []
for f in glob.glob('gen/payload-*.json'):
    p = json.load(open(f))
    grp = 'проекты' if p.get('projects') else ('бренды' if p.get('page_brand') else 'фасеты')
    pages.append(('https://prokompressor.ru' + p.get('url',''), p['slug'], grp))
print(f'страниц к проверке: {len(pages)}', flush=True)

def check(item):
    url, slug, grp = item
    try:
        r = subprocess.run(['curl','-sL','--max-time','25','-A',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126.0','-w','\n%{http_code}',url],
            capture_output=True, timeout=35)
        out = r.stdout.decode('utf-8', errors='ignore')
        code = out.rsplit('\n',1)[-1].strip()
        has = 'expert-byline' in out or 'Материал подготовил' in out
        return (url, slug, grp, code, has)
    except Exception:
        return (url, slug, grp, 'ERR', False)

res = []
with ThreadPoolExecutor(max_workers=6) as ex:
    for i, r in enumerate(ex.map(check, pages), 1):
        res.append(r)
        if i % 100 == 0: print(f'  {i}/{len(pages)}', flush=True)

missing = [r for r in res if not r[4]]
bad_code = [r for r in missing if r[3] not in ('200',)]
from collections import Counter
print(f'\nИТОГ: текст найден на {len(res)-len(missing)}/{len(res)} | ОТСУТСТВУЕТ: {len(missing)}', flush=True)
print('пропуски по группам:', dict(Counter(r[2] for r in missing)))
print('из них не-200 (страница недоступна):', dict(Counter(r[3] for r in bad_code)))
with open('placement-missing.txt','w') as f:
    for url, slug, grp, code, _ in sorted(missing, key=lambda x:(x[2],x[0])):
        f.write(f'{url}\t{grp}\t{code}\n')
json.dump([{'url':r[0],'slug':r[1],'group':r[2],'http':r[3]} for r in missing],
          open('placement-missing.json','w'), ensure_ascii=False, indent=1)
print('=> placement-missing.txt / .json', flush=True)
