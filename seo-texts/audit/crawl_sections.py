# -*- coding: utf-8 -*-
"""Этап 0 аудита: полный обход разделов каталога prokompressor.ru.

Строит реестр с нуля (старому реестру 788 не доверяем) и сразу снимает всё,
что нужно механическим проверкам: метатеги, блок статьи, ссылки из статьи,
фасеты фильтра, пагинацию.

Правило классификации (проверено по sitemap):
  /catalog/<x>/            - глубина 1: почти всегда ТОВАР (27 197 в sitemap товаров),
                             разделов на этой глубине единицы -> сверяем со списком товаров;
  /catalog/<x>/<y>/...     - глубина >=2: РАЗДЕЛ.

Запуск: python3 crawl_sections.py [--limit N]
Результат: audit/inventory.jsonl (одна строка на раздел), audit/crawl-errors.log
"""
import json, os, re, sys, time, html, gzip
import urllib.request, urllib.error
import threading
import concurrent.futures as cf

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, 'inventory.jsonl')
ERR = os.path.join(HERE, 'crawl-errors.log')
SEEN = os.path.join(HERE, '_crawl-seen.json')
UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36'
BASE = 'https://prokompressor.ru'
DELAY = 0.6
WORKERS = 5


def fetch(url, tries=3):
    for i in range(tries):
        try:
            rq = urllib.request.Request(url, headers={
                'User-Agent': UA,
                'Accept': 'text/html,application/xhtml+xml',
                'Accept-Encoding': 'gzip',
            })
            with urllib.request.urlopen(rq, timeout=45) as r:
                raw = r.read()
                if r.headers.get('Content-Encoding') == 'gzip':
                    raw = gzip.decompress(raw)
                return r.status, raw.decode('utf-8', 'replace')
        except urllib.error.HTTPError as e:
            return e.code, ''
        except Exception:
            if i == tries - 1:
                return 0, ''
            time.sleep(2 * (i + 1))
    return 0, ''


def sitemap_urls():
    """Все URL из sitemap: возвращает (все, товары_глубины_1)."""
    st, idx = fetch(BASE + '/sitemap.xml')
    maps = re.findall(r'<loc>(.*?)</loc>', idx)
    allu, prod = set(), set()
    for m in maps:
        st, t = fetch(m)
        us = re.findall(r'<loc>(.*?)</loc>', t)
        allu |= set(us)
        if 'iblock-655' in m:               # инфоблок товаров
            for u in us:
                p = path_of(u)
                if p.startswith('/catalog/') and p.strip('/').count('/') == 1:
                    prod.add(p)
        time.sleep(0.2)
    return allu, prod


def path_of(u):
    return re.sub(r'^https?://[^/]+', '', u).split('#')[0].split('?')[0]


def depth(p):
    return p.strip('/').count('/')


def is_section(p, products):
    """Кандидат в разделы. Точная классификация - после скачивания, по page_kind.

    Раньше глубина 1 отсеивалась по sitemap товаров, но в нём лежат и разделы
    (/catalog/vozdushnye-kompressory/ там есть), из-за чего корневые категории
    выпадали из обхода. Поэтому здесь только грубый фильтр по форме URL.
    """
    if not p.startswith('/catalog/') or not p.endswith('/'):
        return False
    return True


def meta(s, name):
    m = re.search(r'<meta[^>]+name=["\']%s["\'][^>]+content=["\'](.*?)["\']' % name, s, re.S | re.I)
    if not m:
        m = re.search(r'<meta[^>]+content=["\'](.*?)["\'][^>]+name=["\']%s["\']' % name, s, re.S | re.I)
    return html.unescape(m.group(1)).strip() if m else ''


def tag(s, t):
    m = re.search(r'<%s[^>]*>(.*?)</%s>' % (t, t), s, re.S | re.I)
    return html.unescape(re.sub(r'<[^>]+>', ' ', m.group(1))).strip() if m else ''


def extract_article(s):
    """Блок статьи под каталогом: от первого <h2> до конца блока с байлайном.

    На сайте три вида страниц: с нашей статьёй (байлайн «Руспром»),
    с легаси-текстом (h2 есть, байлайна нет), без текста вовсе.
    """
    i = s.find('<h2')
    if i < 0:
        return None
    j = s.find('Руспром')
    if j > i:
        end = s.find('</div>', j)
        block = s[i:end if end > 0 else j + 500]
        kind = 'ours'
    else:
        block = s[i:]
        kind = 'legacy'
    return {'kind': kind, 'html': block}


def facets(s):
    pat = re.compile(r'data-cf-text="([^"]+)"[^>]*>.*?cf-opt__cnt"[^>]*>(\d+)</span>', re.S)
    return {html.unescape(a): int(b) for a, b in pat.findall(s) if int(b) > 0}


def parse(url, s):
    p = path_of(url)
    art = extract_article(s)
    rec = {
        'url': url, 'path': p, 'depth': depth(p),
        'title': tag(s, 'title'), 'description': meta(s, 'description'),
        'h1': tag(s, 'h1'),
        'canonical': (re.search(r'rel=["\']canonical["\'][^>]+href=["\'](.*?)["\']', s, re.I) or [None, ''])[1]
                     if re.search(r'rel=["\']canonical["\']', s, re.I) else '',
        'article_kind': 'none', 'h2': [], 'article_chars': 0, 'article_links': [],
        'has_faq_schema': 'FAQPage' in s, 'has_breadcrumb': 'BreadcrumbList' in s,
        'byline': bool(re.search(r'Руспром', s)),
        'facets': facets(s),
        'pagination_max': max([int(x) for x in re.findall(r'PAGEN_\d+=(\d+)', s)] or [1]),
        'products_on_page': len(re.findall(r'itemprop="name"', s)),
        'page_kind': page_kind(s),
    }
    m = re.search(r'rel=["\']canonical["\'][^>]+href=["\']([^"\']+)', s, re.I)
    rec['canonical'] = m.group(1) if m else ''
    if art:
        b = art['html']
        rec['article_kind'] = art['kind']
        rec['h2'] = [html.unescape(re.sub(r'<[^>]+>', '', x)).strip()
                     for x in re.findall(r'<h2[^>]*>(.*?)</h2>', b, re.S | re.I)]
        txt = html.unescape(re.sub(r'<[^>]+>', ' ', b))
        rec['article_chars'] = len(re.sub(r'\s+', ' ', txt).strip())
        rec['article_links'] = sorted(set(re.findall(r'<a[^>]+href="([^"]+)"', b)))
        rec['article_html'] = b
    return rec


def page_kind(s):
    """Раздел или карточка товара.

    Проверено на живых страницах: у раздела с листингом есть смарт-фильтр
    (MAX_SMART_FILTER / cf-opt__cnt) и ItemList; у карточки товара - одиночная
    схема Product со sku и никакого фильтра. Отдельный случай - раздел-лендинг
    без листинга (например /catalog/azotnye-stantsii/): фильтра нет, но нет и
    схемы Product, поэтому он не путается с карточкой.
    """
    has_filter = 'MAX_SMART_FILTER' in s or 'cf-opt__cnt' in s
    has_list = 'ItemList' in s
    has_product = '"@type": "Product"' in s or '"@type":"Product"' in s
    if has_filter or has_list:
        return 'section'
    if has_product:
        return 'product'
    return 'section_landing'


def links_of(s):
    out = set()
    for m in re.finditer(r'href="(?:https://prokompressor\.ru)?(/catalog/[^"#?]*?/)"', s):
        out.add(m.group(1))
    return out


def main():
    limit = None
    if '--limit' in sys.argv:
        limit = int(sys.argv[sys.argv.index('--limit') + 1])

    print('собираю sitemap...', flush=True)
    allu, products = sitemap_urls()
    print(f'  sitemap: {len(allu)} URL, товаров глубины 1: {len(products)}', flush=True)

    seed = {'/catalog/'}
    for u in allu:
        p = path_of(u)
        if is_section(p, products):
            seed.add(p)
    print(f'  засеяно из sitemap: {len(seed)} разделов', flush=True)

    done = {}
    if os.path.exists(OUT):
        for line in open(OUT, encoding='utf-8'):
            try:
                done[json.loads(line)['path']] = 1
            except Exception:
                pass
        print(f'  уже обойдено ранее: {len(done)}', flush=True)

    frontier = sorted(seed - set(done))
    queued = set(seed)
    fout = open(OUT, 'a', encoding='utf-8')
    ferr = open(ERR, 'a', encoding='utf-8')
    lock = threading.Lock()
    counter = [0]

    def work(p):
        """Скачать раздел, разобрать, вернуть найденные ссылки на разделы."""
        url = BASE + p
        st, s = fetch(url)
        time.sleep(DELAY)
        with lock:
            counter[0] += 1
            if counter[0] % 50 == 0:
                print('  %d обойдено, кандидатов %d' % (counter[0], len(queued)), flush=True)
        if st != 200 or not s:
            with lock:
                ferr.write('%s\t%s\n' % (st, url)); ferr.flush()
            return set()
        cm = re.search(r'rel=["\']canonical["\'][^>]+href=["\']([^"\']+)', s, re.I)
        if cm and cm.group(1).rstrip('/') != url.rstrip('/'):
            time.sleep(1)
            st2, s2 = fetch(url)
            if st2 == 200 and s2:
                s = s2
        rec = parse(url, s)
        rec['http'] = st
        with lock:
            fout.write(json.dumps(rec, ensure_ascii=False) + '\n'); fout.flush()
            done[p] = 1
        return links_of(s)

    rnd = 0
    while frontier:
        rnd += 1
        print('-- волна %d: %d страниц' % (rnd, len(frontier)), flush=True)
        found = set()
        with cf.ThreadPoolExecutor(max_workers=WORKERS) as ex:
            for got in ex.map(work, frontier):
                found |= got
        nxt = []
        for l in sorted(found):
            if l not in queued and is_section(l, products):
                queued.add(l); nxt.append(l)
        frontier = [x for x in nxt if x not in done]
        if limit and counter[0] >= limit:
            break
    n = counter[0]

    fout.close()
    ferr.close()
    json.dump(sorted(queued), open(SEEN, 'w'), ensure_ascii=False)
    print(f'ГОТОВО: обойдено за прогон {n}, всего в реестре {len(done)}, найдено кандидатов {len(queued)}')


if __name__ == '__main__':
    main()
