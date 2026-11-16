"""Шаг 1: найти статьи блога на prokompressor.ru и у конкурентов через sitemap.

python3 blog_urls.py domains.txt  -> urls.jsonl ({domain, url}), резюмируемо по домену.
Статья = URL с сегментом блога/статей и хотя бы одним сегментом после него.
"""
import concurrent.futures as cf
import gzip
import json
import os
import re
import sys

import requests

DIR = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(DIR, 'urls.jsonl')
UA = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                    '(KHTML, like Gecko) Chrome/126.0 Safari/537.36'}
SEG = re.compile(r'/(blog|blogs|stati|statyi|statya|articles?|poleznoe|poleznaya-informatsiya|'
                 r'poleznye-stati|info/stati|publications?|journal|knowledge|baza-znaniy|'
                 r'spravochnik|press-center/articles|sovety|useful|faq-stati|wiki)(/|$)', re.I)
SKIP = re.compile(r'\.(jpg|png|pdf|webp|gif)$|/(tag|tags|page|author|category)/|[?&]PAGEN', re.I)
MAX_SM, MAX_URL = 60, 400


def get(url, t=20):
    r = requests.get(url, headers=UA, timeout=t)
    r.raise_for_status()
    b = r.content
    if url.endswith('.gz') or b[:2] == b'\x1f\x8b':
        b = gzip.decompress(b)
    return b.decode('utf-8', 'ignore')


def sitemaps(dom):
    roots = []
    for base in (f'https://{dom}', f'https://www.{dom}'):
        try:
            rb = get(base + '/robots.txt', 15)
            roots += re.findall(r'(?im)^\s*sitemap:\s*(\S+)', rb)
        except Exception:
            pass
        if roots:
            break
    if not roots:
        roots = [f'https://{dom}/sitemap.xml', f'https://www.{dom}/sitemap.xml']
    return list(dict.fromkeys(roots))


def walk(dom):
    queue, seen, urls = sitemaps(dom), set(), []
    while queue and len(seen) < MAX_SM:
        sm = queue.pop(0)
        if sm in seen:
            continue
        seen.add(sm)
        try:
            x = get(sm)
        except Exception:
            continue
        locs = [l.strip() for l in re.findall(r'<loc>\s*(?:<!\[CDATA\[)?([^<\]]+)', x)]
        if '<sitemapindex' in x:
            # сначала саб-сайтмапы, похожие на блог
            locs.sort(key=lambda u: 0 if re.search(r'blog|stat|art|news|info|iblock|post', u, re.I) else 1)
            queue += locs
            continue
        for u in locs:
            path = re.sub(r'^https?://[^/]+', '', u)
            m = SEG.search(path)
            if m and not SKIP.search(path) and len(path.strip('/').split('/')) > len(path[:m.end()].strip('/').split('/')):
                urls.append(u)
        if len(urls) >= MAX_URL:
            break
    return list(dict.fromkeys(urls))[:MAX_URL]


def main():
    doms = [l.strip() for l in open(sys.argv[1]) if l.strip()]
    done = set()
    if os.path.exists(OUT):
        done = {json.loads(l)['domain'] for l in open(OUT, encoding='utf-8')}
    todo = [d for d in doms if d not in done]
    print(f'доменов {len(doms)}, уже {len(done)}, к обходу {len(todo)}', flush=True)
    with cf.ThreadPoolExecutor(8) as ex, open(OUT, 'a', encoding='utf-8') as f:
        for dom, res in zip(todo, ex.map(lambda d: (lambda: walk(d))() if True else None, todo)):
            f.write(json.dumps({'domain': dom, 'urls': res}, ensure_ascii=False) + '\n')
            f.flush(); os.fsync(f.fileno())
            print(dom, len(res), flush=True)


if __name__ == '__main__':
    main()
