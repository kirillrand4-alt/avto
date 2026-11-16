"""Перелинковка, этап 0: инвентаризация.

  python3 link_inventory.py cats  -> categories.jsonl: все страницы-разделы каталога
        (обход от /catalog/, карточки товаров из sitemap-iblock-655 пропускаются);
        поля url, status, final_url, canonical, noindex, h1, title, crumbs, n_products, sub.
  python3 link_inventory.py blog  -> blog.jsonl: статьи блога с абзацами (нумерованы) и
        уже стоящими внутренними ссылками.
Резюмируемо, fsync.
"""
import collections
import concurrent.futures as cf
import json
import os
import re
import sys
import threading
import time
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

DIR = os.path.dirname(os.path.abspath(__file__))
SITE = 'https://prokompressor.ru'
UA = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                    '(KHTML, like Gecko) Chrome/126.0 Safari/537.36'}
LOCK = threading.Lock()
S = requests.Session()
S.headers.update(UA)


def append(name, rec):
    with LOCK, open(os.path.join(DIR, name), 'a', encoding='utf-8') as f:
        f.write(json.dumps(rec, ensure_ascii=False) + '\n')
        f.flush(); os.fsync(f.fileno())


def jl(name):
    p = os.path.join(DIR, name)
    return [json.loads(l) for l in open(p, encoding='utf-8')] if os.path.exists(p) else []


def norm(u):
    p = urlparse(urljoin(SITE, u))
    if p.netloc not in ('prokompressor.ru', 'www.prokompressor.ru'):
        return None
    path = p.path if p.path.endswith('/') else p.path + '/'
    return path


def products():
    sm = os.path.join(os.path.dirname(DIR), 'sm-iblock-655.xml')
    out = set()
    for u in re.findall(r'<loc>([^<]+)', open(sm, encoding='utf-8').read()):
        path = urlparse(u).path
        if path.count('/') == 3:  # /catalog/slug/
            out.add(path)
    return out


def get(url):
    for i in range(3):
        try:
            time.sleep(0.3)
            return S.get(url, timeout=30)
        except Exception:
            time.sleep(3 * (i + 1))
    return None


def cats(seeds=()):
    prod = products() - set(seeds)
    done = {r['url'] for r in jl('categories.jsonl')}
    queue = collections.deque(['/catalog/'] + [r['url'] for r in jl('categories.jsonl') for _ in [0]])
    seen = set(queue)
    # дочерние ссылки уже обойдённых страниц - повторно в очередь
    for r in jl('categories.jsonl'):
        for s in r.get('sub', []):
            if s not in seen:
                seen.add(s); queue.append(s)
    queue = collections.deque(list(seeds) + [u for u in queue if u not in done and u not in seeds])
    seen |= set(seeds)

    def one(path):
        r = get(SITE + path)
        rec = {'url': path}
        if r is None:
            rec['status'] = 0
            return rec, []
        rec['status'] = r.status_code
        rec['final_url'] = urlparse(r.url).path
        if r.status_code != 200:
            return rec, []
        s = BeautifulSoup(r.text, 'lxml')
        can = s.find('link', rel='canonical')
        rec['canonical'] = urlparse(can['href']).path if can and can.get('href') else ''
        rob = s.find('meta', attrs={'name': 'robots'})
        rec['noindex'] = bool(rob and 'noindex' in (rob.get('content') or '').lower())
        h1 = s.find('h1')
        rec['h1'] = h1.get_text(' ', strip=True) if h1 else ''
        rec['title'] = s.title.get_text(' ', strip=True) if s.title else ''
        bc = s.select('[itemtype*="BreadcrumbList"] [itemprop="name"], .breadcrumbs a, .breadcrumb a')
        rec['crumbs'] = [b.get_text(' ', strip=True) for b in bc][:8]
        links = {norm(a.get('href', '')) for a in s.find_all('a', href=True)}
        links.discard(None)
        cat_links = {l for l in links if l.startswith('/catalog/') and '?' not in l and 'filter' not in l}
        rec['n_products'] = len([l for l in cat_links if l in prod])
        sub = sorted(l for l in cat_links if l not in prod and l.startswith(path) and l != path)
        rec['sub'] = sub
        # разделы из меню/сайдбара тоже кандидаты (не только вложенные)
        other = [l for l in cat_links if l not in prod and l.count('/') >= 3]
        return rec, sorted(set(sub) | set(other))

    n = 0
    with cf.ThreadPoolExecutor(4) as ex:
        while queue:
            batch = [queue.popleft() for _ in range(min(8, len(queue)))]
            for rec, nxt in ex.map(one, batch):
                append('categories.jsonl', rec)
                n += 1
                for l in nxt:
                    if l not in seen:
                        seen.add(l); queue.append(l)
            if n % 100 < 8:
                print(n, 'очередь', len(queue), flush=True)
    print('готово', n)


def blog():
    urls = []
    for d in jl('urls.jsonl'):
        if d['domain'] == 'prokompressor.ru':
            urls = d['urls']
    done = {r['url'] for r in jl('blog.jsonl')}
    todo = [u for u in urls if u not in done]

    def one(u):
        r = get(u)
        rec = {'url': urlparse(u).path}
        if r is None or r.status_code != 200:
            rec['status'] = r.status_code if r is not None else 0
            return rec
        s = BeautifulSoup(r.text, 'lxml')
        for t in s(['script', 'style', 'noscript']):
            t.decompose()
        h1 = s.find('h1')
        rec['h1'] = h1.get_text(' ', strip=True) if h1 else ''
        rec['title'] = s.title.get_text(' ', strip=True) if s.title else ''
        # тело статьи: блок, содержащий h1-соседей с наибольшим числом <p>
        best, bn = None, 0
        for d in s.find_all(['article', 'div', 'section']):
            n = len(d.find_all('p'))
            if n > bn and len(d.find_all('p')) - len(d.find_all('p', recursive=False)) >= 0:
                if d.find('header') is None or n > 3:
                    best, bn = d, n
        # самый глубокий блок, всё ещё держащий >=80% абзацев
        cur = best
        while cur is not None:
            kids = [c for c in cur.find_all(['div', 'section', 'article'], recursive=False)]
            nxt = next((c for c in kids if len(c.find_all('p')) >= 0.8 * bn), None)
            if nxt is None:
                break
            cur = nxt
        body = cur or s.body
        paras, links = [], []
        for el in body.find_all(['h2', 'h3', 'p', 'li', 'td']):
            if el.find_parent(['li', 'td']) and el.name == 'p':
                continue
            tx = el.get_text(' ', strip=True)
            if not tx:
                continue
            paras.append({'n': len(paras), 'tag': el.name, 'text': tx})
            for a in el.find_all('a', href=True):
                p = norm(a['href'])
                if p:
                    links.append({'n': len(paras) - 1, 'href': p, 'anchor': a.get_text(' ', strip=True)})
        rec.update(status=200, paras=paras, links=links,
                   n_words=sum(len(p['text'].split()) for p in paras if p['tag'] != 'h2'))
        return rec

    with cf.ThreadPoolExecutor(4) as ex:
        for rec in ex.map(one, todo):
            append('blog.jsonl', rec)
    print('статей', len(jl('blog.jsonl')))


if __name__ == '__main__':
    if sys.argv[1] == 'seed':  # дообойти разделы, которые sitemap выдаёт за товары
        cats([l.strip() for l in open(sys.argv[2]) if l.strip()])
    else:
        {'cats': cats, 'blog': blog}[sys.argv[1]]()
