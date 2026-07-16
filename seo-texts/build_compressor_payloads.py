# -*- coding: utf-8 -*-
"""Богатый сборщик payload'ов для КОМПРЕССОРНЫХ страниц: роутинг по подтипу (дизель/электро/
поршневой/спиральный/безмасляный), извлечение значения фасета, назначение скелета (S1-S6 для
брендов / F-* для фасетов), привязка проектов по бренду, мост к Enger по типу топлива.

Данные: page-data/*.json (краул) + kb/brand-facts-clean.json (гейт) + projects-index.json (1018 кейсов).
Выход: gen/payload-<slug>.json (category=compressor) + поля guide/typing/skeleton/facet_*/projects.
"""
import json, os, re, glob, hashlib
from collections import defaultdict

import brand_facts_lib as bf

DIR = os.path.dirname(os.path.abspath(__file__))
PD = os.path.join(DIR, 'page-data')
GEN = os.path.join(DIR, 'gen')


def canon(s):
    return re.sub(r'[^a-z0-9]+', '_', str(s).strip().lower()).strip('_')


# --- известные бренды (для отличия бренд-страницы от фасета) ---
_DB = json.load(open(os.path.join(DIR, 'kb', 'brand-facts-clean.json'), encoding='utf-8'))
PROJ = json.load(open(os.path.join(DIR, 'projects-index.json'), encoding='utf-8'))
BRAND_ALIAS = {'atlas copco': 'atlas_copco', 'cross air': 'cross_air', 'et-compressors': 'et_compressors',
               'бежецк': 'bezhetsk', 'зиф': 'zif', 'robushi': 'robuschi', 'airrus': 'rkz'}
KNOWN = set(_DB.keys())
for r in PROJ:
    b = str(r.get('brand', '')).strip().lower()
    if b:
        KNOWN.add(BRAND_ALIAS.get(b, canon(b)))
KNOWN |= {'master_blast', 'robuschi', 'ultratech', 'lupamat', 'zega', 'comprag', 'xeleron',
          'almig', 'mig', 'airpol', 'kraftmachine', 'dalgakiran', 'ekomak', 'airman', 'spitzenreiter'}

# авто-реестр брендов из краула: leaf-слуг, встречающийся в ≥2 секциях каталога, — это бренд
_FACET_LEAF = re.compile(r'^\d|kvt|bar|_l$|_v$|_to_|resiver|osushitel|chastotn|remen|pryam|strana'
                         r'|maslyan|vysokogo|naznach|obemu|bez_|_na_|s_osush|vintovye|porshnev|spiraln'
                         r'|dizelnye|elektrichesk|peredvizh|bezmasl|dvukhstup|buster|po_tipu|smazki'
                         r'|moshchnosti|voltage')
_COUNTRY = {'rossiya', 'germaniya', 'kitay', 'italiya', 'turtsiya', 'belarus', 'chekhiya', 'polsha',
            'belgiya', 'yaponiya', 'frantsiya', 'turtsiya_belgiya'}


def _auto_brands():
    from collections import defaultdict
    sect = defaultdict(set)
    for fn in os.listdir(PD):
        if not fn.endswith('.json') or fn.startswith('_'):
            continue
        d = json.load(open(os.path.join(PD, fn), encoding='utf-8'))
        u = d.get('url', '').replace('https://prokompressor.ru', '')
        seg = [s for s in u.split('/') if s]
        if len(seg) < 3:
            continue
        leaf = canon(seg[-1])
        if _FACET_LEAF.search(leaf) or leaf in _COUNTRY or '_to_' in leaf:
            continue
        sect[leaf].add(seg[1])
    return {l for l, s in sect.items() if len(s) >= 2}


KNOWN |= _auto_brands()

# --- проекты, индексированные по каноническому бренду ---
PROJ_BY_BRAND = defaultdict(list)
for r in PROJ:
    b = str(r.get('brand', '')).strip().lower()
    key = BRAND_ALIAS.get(b, canon(b))
    if key:
        PROJ_BY_BRAND[key].append(r)

# --- мост к Enger по типу топлива ---
ENGER_BRIDGE = {
    'diesel':   '/catalog/vozdushnye-kompressory/po-tipu/vintovye/dizelnye/enger/',
    'electric': '/catalog/vozdushnye-kompressory/po-tipu/vintovye/elektricheskie_1/enger/',
    'general':  '/catalog/vozdushnye-kompressory/enger/',
}

# --- фасетные измерения: (маркер в URL/h1) -> (skeleton, dimension) + экстрактор значения ---
FACET_RULES = [
    ('pressure',  'F-PRESSURE', re.compile(r'(\d+)[\s-]*bar'), re.compile(r'(\d+)\s*бар')),
    ('power',     'F-POWER',    re.compile(r'(\d[\d.]*)[\s-]*kvt'), re.compile(r'(\d[\d.,]*)\s*квт')),
    # perf ДО receiver: «N-l-min»/«N л/мин» это производительность, а не объём ресивера.
    # receiver-регексы (l-/л\b) иначе ловят l-min и «л/мин» первыми и роняют dim в receiver.
    ('perf',      'F-PERF',     re.compile(r'(\d+)[\s-]*l[-\s]*min'), re.compile(r'(\d+)\s*л\s*/?\s*мин')),
    ('receiver',  'F-RECEIVER', re.compile(r'(\d+)[\s-]*l(?:itr|\b)(?!-?\s*min)'), re.compile(r'(\d+)\s*л(?![/\s]*мин)\b')),
    ('voltage',   'F-VOLTAGE',  re.compile(r'(\d+)[\s-]*v\b'), re.compile(r'(\d+)\s*в\b')),
]


def detect_type(h1, url):
    """Вернуть (form, fuel, special, guide, typing, topic_word)."""
    s = (h1 or '') + ' ' + url
    low = s.lower()
    form = 'screw'
    if 'поршнев' in low or 'porshnev' in low: form = 'piston'
    elif 'спиральн' in low or 'spiraln' in low: form = 'spiral'
    fuel = None
    if 'дизель' in low or 'дизельн' in low or 'dizelnye' in low or 'peredvizh' in low or 'передвижн' in low:
        fuel = 'diesel'
    elif 'электрич' in low or 'elektrichesk' in low:
        fuel = 'electric'
    special = []
    if 'безмасл' in low or 'bezmasl' in low: special.append('oilfree')
    if 'двухступен' in low or 'dvukhstup' in low: special.append('two_stage')
    if 'бустер' in low or 'buster' in low or 'дожимн' in low: special.append('booster')

    # выбор гайда: дизельный винтовой -> дизельный гайд; всё прочее -> электро/общий гайд
    if form == 'screw' and fuel == 'diesel':
        guide = 'gen/STYLE-GUIDE.md'
    else:
        guide = 'gen/STYLE-GUIDE-ELEKTRO.md'

    # типизация H2 (для QA): что обязано стоять во вводном H2
    grp = [('компрессор',)]
    if form == 'screw': grp.append(('винтов',))
    elif form == 'piston': grp = [('поршнев',), ('компрессор',)]
    elif form == 'spiral': grp = [('спиральн',), ('компрессор',)]
    if fuel == 'diesel': grp.append(('дизель', 'передвижн'))
    elif fuel == 'electric': grp.append(('электрич',))
    typing = grp
    topic = {'piston': 'поршневых компрессоров', 'spiral': 'спиральных компрессоров'}.get(
        form, ('дизельных винтовых компрессоров' if fuel == 'diesel'
               else 'электрических винтовых компрессоров' if fuel == 'electric'
               else 'винтовых компрессоров'))
    return form, fuel, special, guide, typing, topic


def detect_facet(h1, url):
    """Вернуть (skeleton, dimension, value_str) или (None,None,None) если не фасет по значению."""
    low = (url + ' ' + (h1 or '')).lower()
    for dim, skel, ure, hre in FACET_RULES:
        m = ure.search(url.lower()) or hre.search((h1 or '').lower())
        if m:
            unit = {'pressure': 'бар', 'power': 'кВт', 'receiver': 'л', 'perf': 'л/мин', 'voltage': 'В'}[dim]
            return skel, dim, f'{m.group(1)} {unit}'
    if any(k in low for k in ('remen', 'ременн', 'pryam', 'прямой привод', 'privod')):
        return 'F-DRIVE', 'drive', ('ременной' if 'remen' in low or 'ременн' in low else 'прямой')
    if any(k in low for k in ('rossiya', 'россия', 'germaniya', 'германи', 'kitay', 'кита', 'italiya',
                              'итали', 'turtsiya', 'турци', 'belarus', 'беларус', 'chekhiya', 'чехи',
                              'polsha', 'польш', 'belgiya', 'бельги', 'yaponiya', 'япони', 'frantsiya',
                              'strana', 'proizvodstv', 'po-strane')):
        return 'F-COUNTRY', 'country', None
    if 'chastotn' in low or 'vsd' in low or 'частотн' in low:
        return 'F-VSD', 'vsd', None
    if 'naznacheniyu' in low or 'vyduv' in low or 'выдув' in low or 'pet' in low:
        return 'F-APPLICATION', 'application', None
    if 'buster' in low or 'бустер' in low or 'dozhimn' in low:
        return 'F-BOOSTER', 'booster', None
    if 'dvukhstup' in low or 'двухступен' in low:
        return 'F-2STAGE', '2stage', None
    return None, None, None


SKELETONS = ['S1', 'S2', 'S3', 'S4', 'S5', 'S6']


def brand_skeleton(brand_key):
    if brand_key == 'enger':
        return 'ENGER'
    h = int(hashlib.md5(brand_key.encode()).hexdigest(), 16)
    return SKELETONS[h % len(SKELETONS)]


try:
    _PHOTOS = json.load(open(os.path.join(DIR, 'projects-photos.json'), encoding='utf-8'))
except FileNotFoundError:
    _PHOTOS = {}


def pick_projects(brand_key, n=3):
    ps = PROJ_BY_BRAND.get(brand_key, [])
    out = []
    for r in ps[:n]:
        rel = r['url'].replace('https://prokompressor.ru', '')
        item = {
            'url': rel, 'equipment': r.get('equipment'), 'client': r.get('client'),
            'city': r.get('city') or r.get('city_guess'), 'sphere': r.get('sphere'),
        }
        if _PHOTOS.get(rel):
            item['photo_url'] = _PHOTOS[rel]
        out.append(item)
    return out


def build_one(d):
    url = d['url']; rel = url.replace('https://prokompressor.ru', '')
    h1 = d.get('h1')
    tail = BRAND_ALIAS.get(canon(url.rstrip('/').split('/')[-1]), canon(url.rstrip('/').split('/')[-1]))
    is_brand = tail in KNOWN
    brand_key = tail if is_brand else None

    form, fuel, special, guide, typing, topic = detect_type(h1, url)
    tier = bf.tone_for(brand_key) if brand_key else 'neytralnyy'

    pl = {
        'slug': d['slug'], 'url': rel, 'h1': h1, 'title_current': d.get('title_current'),
        'category': 'compressor', 'tier': tier, 'guide': guide, 'typing': typing, 'topic': topic,
        'form': form, 'fuel': fuel, 'special': special,
        'count': d.get('count'), 'count_note': 'число позиций С УЧЁТОМ ИСПОЛНЕНИЙ, не уникальных моделей',
        'price_min': d.get('price_min'), 'price_max': d.get('price_max'),
        'sample_models': d.get('sample_models', [])[:12], 'page_brand': brand_key,
    }
    if is_brand:
        if bf.has_brand(brand_key):
            pl['brand_facts'] = bf.fact_block(brand_key)   # гейт: факты только для подтверждённых
        pr = pick_projects(brand_key)
        if pr:
            pl['projects'] = pr
        pl['skeleton'] = brand_skeleton(brand_key)
    else:
        skel, dim, val = detect_facet(h1, url)
        # свести к скелетам, которые стайлгайд ЗНАЕТ (иначе модель импровизирует структуру)
        KNOWN_SKEL = {'F-POWER', 'F-PRESSURE', 'F-PERF', 'F-DRIVE', 'F-COUNTRY', 'F-EQUIP'}
        skel = skel if skel in KNOWN_SKEL else 'F-EQUIP'   # receiver/voltage/vsd/booster/2stage/generic -> комплектация
        pl['skeleton'] = skel
        pl['facet_dimension'] = dim or 'комплектация'
        pl['facet_value'] = val
        pl['facet_note'] = ('страница продаёт именно этот срез каталога; веди текст от значения '
                            'фасета, не агитируй за другие') if dim else None

    # мост к Enger (кроме страниц самого Enger и родного тира)
    if brand_key != 'enger' and tier != 'rodnoy':
        pl['enger_category_url'] = ENGER_BRIDGE.get(fuel or 'general')
    return pl


def main():
    import sys
    only_limit = None
    for i, a in enumerate(sys.argv):
        if a == '--limit': only_limit = int(sys.argv[i + 1])
    pages = []
    for fn in os.listdir(PD):
        if fn.endswith('.json') and not fn.startswith('_'):
            d = json.load(open(os.path.join(PD, fn), encoding='utf-8'))
            if d.get('status') == 'OK':
                # авторитетная категоризация как в build_payloads
                u = d['url'].replace('https://prokompressor.ru', '')
                if u.split('/')[2:3] == ['vozdushnye-kompressory']:
                    pages.append(d)
    if only_limit:
        pages = pages[:only_limit]
    from collections import Counter
    stats = Counter(); n = 0
    for d in pages:
        pl = build_one(d)
        json.dump(pl, open(os.path.join(GEN, f'payload-{pl["slug"]}.json'), 'w'), ensure_ascii=False, indent=1)
        n += 1
        stats['brand' if pl.get('brand_facts') else 'facet'] += 1
        stats['with_projects' if pl.get('projects') else '_'] += 1
        stats[pl['skeleton']] += 1
        stats['guide_' + ('diesel' if pl['guide'].endswith('GUIDE.md') else 'electric')] += 1
    print(f'компрессорных payload: {n}')
    print('брендовых:', stats['brand'], '| фасетных:', stats['facet'], '| с проектами:', stats['with_projects'])
    print('гайды:', {k: v for k, v in stats.items() if k.startswith('guide_')})
    print('скелеты:', {k: v for k, v in stats.items() if k.startswith(('S', 'F', 'E'))})


if __name__ == '__main__':
    main()
