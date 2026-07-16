# -*- coding: utf-8 -*-
"""Автосбор данных живых страниц каталога prokompressor.ru (детерминированный, БЕЗ LLM).
Aspro Max рендерит на сервере -> парсим regex'ом. Сырой HTML НЕ храним (664КБ×763 = не влезет),
сохраняем только компактный extract. Резюмируемо: уже собранные slug пропускаем.

Выход: page-data/<slug>.json + page-data/_index.json (сводка).
Фолбэк на Fable (провайдерский API) — отдельным скриптом только для страниц со status=PARSE_FAIL."""
import csv, json, os, re, sys, time
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests

DIR = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(DIR, 'page-data')
os.makedirs(OUT, exist_ok=True)
UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36'

# тип категории по пути URL (совпадает с ключами гайда/QA)
def categorize(url):
    """Секция-в-первую-очередь (верхний сегмент пути важнее подстрок глубже)."""
    u = url.replace('https://prokompressor.ru', '')
    seg = [x for x in u.split('/') if x]
    section = seg[1] if len(seg) > 1 else ''
    sub = seg[2] if len(seg) > 2 else ''
    if section == 'vozdushnye-kompressory':
        return 'compressor'
    if section == 'osushiteli':
        if sub == 'adsorbtsionnye': return 'ads_dryer'
        if sub == 'refrizheratornye': return 'ref_dryer'
        return 'dryer_other'
    if section == 'resivery':
        return 'receiver'
    if section == 'podgotovka-vozdukha':
        if sub in ('filtry-magistralnye', 'ugolnye-kolonny'): return 'filter'
        if sub in ('separatory-tsentrobezhnye-tsiklonnye', 'maslovlagorazdeliteli'): return 'separator'
        return 'air_prep'
    if section == 'zapasnye-chasti-i-raskhodniki':
        return 'spare_parts'
    if section == 'raskhodomery-i-datchiki':
        return 'flowmeter'
    if section == 'generatsiya-gazov':
        if sub == 'generatory-azota': return 'n2_gen'
        if sub == 'generatory-kisloroda': return 'o2_gen'
        return 'gas_other'
    return 'other'

# бренд-слуг из хвоста URL, если это брендовый фасет (последний сегмент — известный бренд-слуг)
BRAND_TAIL = re.compile(r'/([a-z0-9][a-z0-9_-]{1,30})/?$')


def slugify(url):
    parts = [p for p in url.rstrip('/').split('/') if p]
    return '__'.join(parts[-3:]) if len(parts) >= 3 else parts[-1]


def parse(html, url):
    def m1(pat, s=html, fl=re.S):
        m = re.search(pat, s, fl); return m.group(1).strip() if m else None
    title = m1(r'<title>(.*?)</title>')
    meta = m1(r'<meta name="description" content="(.*?)"', html, 0)
    h1raw = m1(r'<h1[^>]*>(.*?)</h1>')
    h1 = re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', '', h1raw)).strip() if h1raw else None

    # счётчик и мин.цена — из meta («N товаров, цены от X ₽») либо со страницы
    count = None; meta_min = None
    cbody = re.search(r'([\d][\d\s\u00a0]{0,10})\s*товар', html)   # «N товаров» из тела (надёжнее meta)
    if cbody:
        v = int(re.sub(r'\D', '', cbody.group(1)))
        if v: count = v
    if count is None:
        pg = re.findall(r'PAGEN_\d+=(\d+)', html)              # запасной нижний порог: страниц*20
        if pg: count = max(int(x) for x in pg) * 20
    p = re.search(r'от\s*([\d\s\u00a0]+)\s*₽', meta or '')
    if p: meta_min = int(re.sub(r'\D', '', p.group(1)))

    # цены листинга из data-value на price-дивах
    prices = sorted(set(int(v) for v in re.findall(r'class="price[^"]*"[^>]*data-value="(\d+)"', html)))
    prices = [p for p in prices if 500 <= p <= 100000000]

    # модели листинга (itemprop=name; первые записи — хлебные крошки, отсекаем по вхождению h1/Каталог)
    names = [re.sub(r'\s+', ' ', n).replace('&quot;', '"').strip()
             for n in re.findall(r'itemprop="name"[^>]*>(.*?)<', html, re.S)]
    crumbs = {'Главная', 'Каталог'}
    models = [n for n in names if n not in crumbs and n != h1 and len(n) > 4
              and re.search(r'\d', n)][:20]   # у настоящих моделей есть цифровой код серии

    # брендовые фасеты из сайдбара (ссылки того же раздела на один сегмент глубже)
    base = url.rstrip('/')
    facet = re.findall(re.escape(base) + r'/([a-z0-9][a-z0-9_-]{1,30})/["?]', html)
    brand_facets = list(dict.fromkeys(facet))

    # является ли САМА страница брендовым фасетом
    cat_bases = ('refrizheratornye', 'adsorbtsionnye', 'osushiteli', 'osushiteli-vozdukha', 'resivery',
                 'filtry-magistralnye', 'filtry', 'generatory-azota', 'generatory-kisloroda',
                 'generatsiya-gazov', 'vintovye', 'porshnevye', 'spiralnye', 'po-tipu', 'po-tipu-smazki',
                 'po-proizvoditelyu', 'elektricheskie_1', 'dizelnye', 'podgotovka-vozdukha',
                 'vozdushnye-kompressory', 'catalog', 'separatory', 'vlagomaslootdeliteli',
                 'zapchasti', 'raskhodniki', 'raskhodomery', 'bezmaslyanye_1')
    tail = url.rstrip('/').split('/')[-1]
    page_brand = tail if (tail not in cat_bases and re.match(r'^[a-z0-9][a-z0-9_-]*$', tail)
                          and '-bar' not in tail and '-l-min' not in tail and 'kompressory-' not in tail) else None

    if count is None and models:
        count = len(models)          # нижний порог: показанные позиции (когда счётчика/пагинации нет)
    ok = bool(h1 and (count or models))
    return {
        'url': url, 'slug': slugify(url), 'category': categorize(url),
        'h1': h1, 'title_current': title, 'meta_current': meta,
        'count': count, 'price_min': meta_min or (prices[0] if prices else None),
        'price_max': prices[-1] if prices else None,
        'prices_sample': prices[:12],
        'sample_models': models, 'brand_facets': brand_facets, 'page_brand': page_brand,
        'status': 'OK' if ok else 'PARSE_FAIL',
    }


def fetch_one(url, retries=3):
    slug = slugify(url)
    dst = os.path.join(OUT, slug + '.json')
    if os.path.exists(dst):
        return slug, 'cached'
    err = None
    for a in range(retries):
        try:
            r = requests.get(url, headers={'User-Agent': UA}, timeout=30)
            if r.status_code == 200 and len(r.text) > 2000:
                data = parse(r.text, url)
                json.dump(data, open(dst, 'w'), ensure_ascii=False, indent=1)
                return slug, data['status']
            err = f'HTTP {r.status_code} len={len(r.text)}'
        except Exception as ex:
            err = repr(ex)[:120]
        time.sleep(1.5 * (a + 1))
    json.dump({'url': url, 'slug': slug, 'category': categorize(url), 'status': 'FETCH_FAIL', 'error': err},
              open(dst, 'w'), ensure_ascii=False, indent=1)
    return slug, 'FETCH_FAIL'


def load_worklist():
    rows = list(csv.reader(open(os.path.join(DIR, 'inventory/text-audit.csv')), delimiter=';'))
    hdr = [h.lstrip('﻿') for h in rows[0]]
    data = [dict(zip(hdr, r)) for r in rows[1:] if r]
    return [d['url'] for d in data if d['status'] == 'NO_TEXT' or d['status'].startswith('DUP')]


def main():
    urls = load_worklist()
    limit = None
    for i, a in enumerate(sys.argv):
        if a == '--limit': limit = int(sys.argv[i + 1])
    if limit: urls = urls[:limit]
    print(f'страниц к сбору: {len(urls)}', file=sys.stderr)
    done = {}
    with ThreadPoolExecutor(max_workers=8) as ex:
        futs = {ex.submit(fetch_one, u): u for u in urls}
        for i, f in enumerate(as_completed(futs), 1):
            slug, st = f.result()
            done[st] = done.get(st, 0) + 1
            if i % 25 == 0 or i == len(urls):
                print(f'  {i}/{len(urls)} {done}', file=sys.stderr)
    # индекс
    idx = []
    for fn in os.listdir(OUT):
        if fn.endswith('.json') and not fn.startswith('_'):
            idx.append(json.load(open(os.path.join(OUT, fn))))
    json.dump(idx, open(os.path.join(OUT, '_index.json'), 'w'), ensure_ascii=False, indent=1)
    from collections import Counter
    print('ИТОГ статусы:', dict(Counter(x['status'] for x in idx)), file=sys.stderr)
    print('по категориям:', dict(Counter(x['category'] for x in idx)), file=sys.stderr)


if __name__ == '__main__':
    main()
