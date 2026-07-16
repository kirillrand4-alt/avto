# -*- coding: utf-8 -*-
"""Массовый сборщик payload'ов: page-data (краул) + брендовые факты (гейт достоверности) +
досье категории -> gen/payload-<slug>.json, готовый для gen_provider.py.

Гейт: брендовая фактура ТОЛЬКО из brand_facts_lib (safe_facts + подтверждённые зависимости +
охранный блок caveats). Некомпрессорным страницам подкладываем category_reference из досье.
Мост к Enger — по правилу стайлгайда (осушители/генераторы/фильтры — да; ресиверы/сепараторы/запчасти — нет).
"""
import json, os, re, sys
from collections import Counter, defaultdict

import brand_facts_lib as bf

DIR = os.path.dirname(os.path.abspath(__file__))
PD = os.path.join(DIR, 'page-data')
OUTDIR = os.path.join(DIR, 'gen')
os.makedirs(OUTDIR, exist_ok=True)

# корневые URL категорий (для перелинковки «по месту в системе»)
ROOTS = {
    'dryer':   '/catalog/osushiteli/',
    'ref_dryer':'/catalog/osushiteli/refrizheratornye/',
    'ads_dryer':'/catalog/osushiteli/adsorbtsionnye/',
    'receiver':'/catalog/resivery/',
    'filter':  '/catalog/podgotovka-vozdukha/filtry-magistralnye/',
    'air_prep':'/catalog/podgotovka-vozdukha/',
    'n2_gen':  '/catalog/generatsiya-gazov/generatory-azota/',
    'o2_gen':  '/catalog/generatsiya-gazov/generatory-kisloroda/',
}
# соседи по цепочке подготовки воздуха (related_urls для перелинковки)
NEIGHBORS = {
    'ref_dryer': ['receiver', 'filter'], 'ads_dryer': ['ref_dryer', 'filter'],
    'dryer_other': ['receiver', 'filter'], 'receiver': ['ref_dryer', 'filter'],
    'filter': ['ref_dryer', 'receiver'], 'separator': ['filter', 'ref_dryer'],
    'n2_gen': ['ref_dryer', 'filter'], 'o2_gen': ['ref_dryer', 'filter'],
    'air_prep': ['ref_dryer', 'receiver', 'filter'], 'gas_other': ['n2_gen', 'o2_gen'],
    'spare_parts': [], 'flowmeter': ['filter'],
}
# тип категории -> ключ досье category-ref/index.json
REFKEY = {'ref_dryer': 'ref_dryer', 'ads_dryer': 'ads_dryer', 'dryer_other': 'ref_dryer',
          'receiver': 'receiver', 'filter': 'filter', 'separator': 'separator',
          'n2_gen': 'n2_gen', 'o2_gen': 'o2_gen', 'air_prep': 'air_prep',
          'spare_parts': 'spare_parts', 'flowmeter': 'flowmeter'}
SKELETON = {'ref_dryer': 'DRY', 'ads_dryer': 'DRY', 'dryer_other': 'DRY', 'receiver': 'REC',
            'filter': 'FLT', 'separator': 'FLT', 'n2_gen': 'GAS', 'o2_gen': 'GAS',
            'air_prep': 'FLT', 'spare_parts': 'SPR', 'flowmeter': 'FLT'}
# категории, где у Enger есть товар -> мост уместен
BRIDGE_CATS = {'ref_dryer', 'ads_dryer', 'dryer_other', 'filter', 'n2_gen', 'o2_gen'}
# суффиксы брендовых слугов на некомпрессорных фасетах (снять перед поиском фактов)
BRAND_SUFFIX = re.compile(r'_(osush|osushiteli|resiver|resivery|filtr|filtry|separator|generator)$')

REF_INDEX = json.load(open(os.path.join(DIR, 'kb', 'category-ref', 'index.json'), encoding='utf-8'))


def categorize(url):
    """Секция-в-первую-очередь: верхний сегмент пути важнее подстрок глубже.
    Иначе «kompressory-s-resiverom» ловится как receiver (баг)."""
    u = url.replace('https://prokompressor.ru', '')
    seg = [s for s in u.split('/') if s]
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
        if sub == 'filtry-magistralnye' or sub == 'ugolnye-kolonny': return 'filter'
        if sub in ('separatory-tsentrobezhnye-tsiklonnye', 'maslovlagorazdeliteli'): return 'separator'
        return 'air_prep'          # dookhladiteli, kondensatootvodchiki, корень
    if section == 'zapasnye-chasti-i-raskhodniki':
        return 'spare_parts'
    if section == 'raskhodomery-i-datchiki':
        return 'flowmeter'
    if section == 'generatsiya-gazov':
        if sub == 'generatory-azota': return 'n2_gen'
        if sub == 'generatory-kisloroda': return 'o2_gen'
        return 'gas_other'
    return 'other'


def norm_brand(page_brand):
    if not page_brand:
        return None
    b = BRAND_SUFFIX.sub('', page_brand)
    b = re.sub(r'_\d+$', '', b)        # enger_2 -> enger (дизамбигуация фасета)
    b = b.replace('-', '_')
    return b


def load_pages():
    pages = []
    for fn in os.listdir(PD):
        if fn.endswith('.json') and not fn.startswith('_'):
            d = json.load(open(os.path.join(PD, fn), encoding='utf-8'))
            if d.get('status') in ('OK',):
                d['category'] = categorize(d['url'])   # авторитетная категоризация (секция-first)
                pages.append(d)
    return pages


def build_enger_map(pages):
    """категория -> URL головного брендового фасета Enger (кратчайший путь, не под-фасет)."""
    m = {}
    for d in pages:
        if norm_brand(d.get('page_brand')) == 'enger':
            u = d['url'].replace('https://prokompressor.ru', '')
            if d['category'] not in m or len(u) < len(m[d['category']]):
                m[d['category']] = u
    return m


def build_related_map(pages):
    """категория -> корневой URL раздела: канонический ROOTS, если такой URL реально в крауле;
    иначе берём страницу этой категории с кратчайшим путём (ближе всего к корню)."""
    live = {p['url'].replace('https://prokompressor.ru', '') for p in pages}
    roots = {}
    # 1) канонические корни, подтверждённые краулом
    for cat, r in ROOTS.items():
        if r in live:
            roots[cat] = r
    # 2) для остального — кратчайший путь категории
    for d in pages:
        cat = d['category']; u = d['url'].replace('https://prokompressor.ru', '')
        if cat in roots:
            continue
        if cat not in roots or len(u) < len(roots.get(cat, 'x' * 999)):
            roots[cat] = u
    return roots


def rel_path(u):
    return u.replace('https://prokompressor.ru', '')


def make_payload(d, enger_map, roots_live):
    cat = d['category']
    brand_slug = norm_brand(d.get('page_brand'))
    is_brand = brand_slug and bf.has_brand(brand_slug)
    tier = bf.tone_for(brand_slug) if brand_slug else 'neytralnyy'

    pl = {
        'slug': d['slug'], 'url': rel_path(d['url']), 'h1': d['h1'],
        'title_current': d.get('title_current'), 'category': cat, 'tier': tier,
        'skeleton': SKELETON.get(cat, 'compressor' if cat == 'compressor' else 'FLT'),
        'count': d.get('count'),
        'count_note': 'число позиций С УЧЁТОМ ИСПОЛНЕНИЙ, не уникальных моделей',
        'price_min': d.get('price_min'), 'price_max': d.get('price_max'),
        'sample_models': d.get('sample_models', [])[:12],
        'brand_facets': d.get('brand_facets', []),
        'page_brand': brand_slug,
    }
    # брендовая фактура через гейт достоверности
    if is_brand:
        pl['brand_facts'] = bf.fact_block(brand_slug)
    # некомпрессорные: досье категории + перелинковка + мост
    if cat != 'compressor':
        rk = REFKEY.get(cat)
        if rk and rk in REF_INDEX:
            pl['category_reference'] = REF_INDEX[rk]
        related = []
        for nb in NEIGHBORS.get(cat, []):
            u = roots_live.get(nb) or ROOTS.get(nb)
            if u and rel_path(u) != pl['url']:
                related.append(rel_path(u))
        pl['related_urls'] = related
        if cat in BRIDGE_CATS:
            eu = enger_map.get(cat)
            if eu and eu != pl['url']:
                pl['enger_category_url'] = eu
    return pl


def main():
    only = None
    for i, a in enumerate(sys.argv):
        if a == '--category': only = sys.argv[i + 1]
        if a == '--limit': pass
    pages = load_pages()
    enger_map = build_enger_map(pages)
    roots_live = build_related_map(pages)
    if only:
        pages = [p for p in pages if p['category'] == only]
    n = 0; stats = Counter()
    for d in pages:
        pl = make_payload(d, enger_map, roots_live)
        out = os.path.join(OUTDIR, f'payload-{pl["slug"]}.json')
        json.dump(pl, open(out, 'w'), ensure_ascii=False, indent=1)
        n += 1
        stats[pl['category']] += 1
        stats['brand_pages' if pl.get('brand_facts') else 'facet_pages'] += 1
        stats['with_bridge' if pl.get('enger_category_url') else '_'] += 1
    print(f'payload собрано: {n}')
    print('enger-мост доступен для категорий:', enger_map)
    print('по категориям:', {k: v for k, v in stats.items() if k not in ('brand_pages', 'facet_pages', 'with_bridge', '_')})
    print(f'брендовых: {stats["brand_pages"]} | фасетных: {stats["facet_pages"]} | с мостом Enger: {stats["with_bridge"]}')


if __name__ == '__main__':
    main()
