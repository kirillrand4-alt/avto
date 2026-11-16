"""Шаг 2: скачать статьи из urls.jsonl -> pages.jsonl (резюмируемо по url, fsync).

Поля: domain, url, title, h1, heads (h2/h3 по порядку), text (чистый текст основной части,
до 20000 симв.), n_chars, err.
"""
import concurrent.futures as cf
import json
import os
import re
import threading
import time

import requests
from bs4 import BeautifulSoup

DIR = os.path.dirname(os.path.abspath(__file__))
SRC, OUT = os.path.join(DIR, 'urls.jsonl'), os.path.join(DIR, 'pages.jsonl')
UA = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                    '(KHTML, like Gecko) Chrome/126.0 Safari/537.36'}
LOCK = threading.Lock()
_last = {}


def polite(dom):
    # не чаще запроса в 1 с на домен
    with LOCK:
        t = max(0, _last.get(dom, 0) + 1.0 - time.time())
        _last[dom] = time.time() + t
    time.sleep(t)


def parse(html):
    s = BeautifulSoup(html, 'lxml')
    for t in s(['script', 'style', 'noscript', 'svg', 'form', 'iframe']):
        t.decompose()
    title = (s.title.get_text(' ', strip=True) if s.title else '')[:300]
    h1 = s.find('h1')
    h1 = h1.get_text(' ', strip=True)[:300] if h1 else ''
    # основная часть: article/main, иначе блок с наибольшим числом <p>
    root = s.find('article') or s.find('main')
    if not root:
        best, bn = s.body or s, 0
        for d in s.find_all(['div', 'section']):
            n = len(d.find_all('p', recursive=False))
            if n > bn:
                best, bn = d, n
        root = best
    for t in root.find_all(['nav', 'header', 'footer', 'aside']):
        t.decompose()
    heads = [h.get_text(' ', strip=True)[:200] for h in root.find_all(['h2', 'h3'])][:60]
    parts = []
    for el in root.find_all(['h2', 'h3', 'h4', 'p', 'li', 'td', 'th']):
        tx = el.get_text(' ', strip=True)
        if tx:
            parts.append(('## ' if el.name in ('h2', 'h3', 'h4') else '') + tx)
    text = re.sub(r'\n{2,}', '\n', '\n'.join(dict.fromkeys(parts)))
    return title, h1, heads, text


def fetch(dom, url):
    polite(dom)
    rec = {'domain': dom, 'url': url}
    try:
        r = requests.get(url, headers=UA, timeout=25)
        if r.status_code != 200:
            rec['err'] = f'HTTP {r.status_code}'
            return rec
        r.encoding = r.apparent_encoding if not r.encoding or r.encoding.lower() == 'iso-8859-1' else r.encoding
        title, h1, heads, text = parse(r.text)
        rec.update(title=title, h1=h1, heads=heads, text=text[:20000], n_chars=len(text))
    except Exception as e:
        rec['err'] = repr(e)[:200]
    return rec


def main():
    jobs = [(d['domain'], u) for d in map(json.loads, open(SRC, encoding='utf-8')) for u in d['urls']]
    done = set()
    if os.path.exists(OUT):
        done = {json.loads(l)['url'] for l in open(OUT, encoding='utf-8')}
    todo = [j for j in jobs if j[1] not in done]
    print(f'статей {len(jobs)}, есть {len(done)}, к скачиванию {len(todo)}', flush=True)
    with cf.ThreadPoolExecutor(16) as ex, open(OUT, 'a', encoding='utf-8') as f:
        for i, rec in enumerate(ex.map(lambda j: fetch(*j), todo), 1):
            with LOCK:
                f.write(json.dumps(rec, ensure_ascii=False) + '\n')
                f.flush(); os.fsync(f.fileno())
            if i % 100 == 0:
                print(i, flush=True)


if __name__ == '__main__':
    main()
