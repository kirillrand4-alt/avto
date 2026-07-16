# -*- coding: utf-8 -*-
"""До-краул карточек товаров: пары имя↔ссылка↔цена по каждой странице (для ItemList+Product schema).
Детерминированный, БЕЗ LLM. Выход: products-index.json {slug: [{name,url,price}, …]} (до 24 карточек)."""
import json, os, re, glob
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests

DIR = os.path.dirname(os.path.abspath(__file__))
UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36'
SITE = 'https://prokompressor.ru'
OUT = os.path.join(DIR, 'products-index.json')

# (url, name) — надёжная пара из <a href=… itemprop="url"> … <span itemprop="name">NAME
ITEM = re.compile(r'href="([^"]+)"\s+itemprop="url"[^>]*>\s*<span itemprop="name">([^<]+)</span>', re.S)
PRICE = re.compile(r'class="price[^"]*"[^>]*data-value="(\d+)"')


def one(slug, url):
    try:
        h = requests.get(url, headers={'User-Agent': UA}, timeout=30).text
    except Exception:
        return slug, []
    items = [(u, re.sub(r'\s+', ' ', n).replace('&quot;', '"').strip()) for u, n in ITEM.findall(h)]
    prices = [int(x) for x in PRICE.findall(h)]
    prices = [p for p in prices if 500 <= p <= 100000000]
    out = []
    for i, (u, n) in enumerate(items[:24]):
        rec = {'name': n, 'url': u if u.startswith('/') else '/' + u.split(SITE)[-1]}
        if len(prices) == len(items) and i < len(prices):
            rec['price'] = prices[i]
        out.append(rec)
    return slug, out


def main():
    pages = {}
    for f in glob.glob(os.path.join(DIR, 'gen', 'payload-*.json')):
        d = json.load(open(f))
        pages[d['slug']] = SITE + d['url']
    res = {}
    with ThreadPoolExecutor(max_workers=8) as ex:
        futs = {ex.submit(one, s, u): s for s, u in pages.items()}
        for i, fut in enumerate(as_completed(futs), 1):
            s, out = fut.result()
            if out:
                res[s] = out
            if i % 100 == 0:
                print(f'  {i}/{len(pages)}', flush=True)
    json.dump(res, open(OUT, 'w'), ensure_ascii=False)
    withprice = sum(1 for v in res.values() if v and 'price' in v[0])
    print(f'страниц с карточками: {len(res)} | из них с ценами: {withprice}')


if __name__ == '__main__':
    main()
