# -*- coding: utf-8 -*-
"""Готовит досье на страницу для агента-ревьюера.

Всё, что нужно для содержательных проверок (соответствие странице, польза,
достоверность), кладём в один файл, чтобы агент не собирал данные заново.
"""
import json, os, re, glob, html

HERE = os.path.dirname(os.path.abspath(__file__))
GEN = os.path.join(HERE, '..', 'gen')
BRIEFS = os.path.join(HERE, 'briefs')
os.makedirs(BRIEFS, exist_ok=True)

REF_LIMIT = 3500
FACTS_LIMIT = 3000


def plain(h):
    t = html.unescape(re.sub(r'<[^>]+>', '\n', h or ''))
    return re.sub(r'\n{2,}', '\n', re.sub(r'[ \t]+', ' ', t)).strip()


def slug_of(path):
    s = path.strip('/').replace('catalog/', '', 1).replace('/', '__')
    return s or 'catalog-root'


def main():
    inv = [json.loads(l) for l in open(os.path.join(HERE, 'inventory.jsonl'), encoding='utf-8') if l.strip()]
    keys = json.load(open(os.path.join(HERE, 'keys-by-url.json')))
    cann = json.load(open(os.path.join(HERE, 'cannibals.json')))
    chk = {}
    cp = os.path.join(HERE, 'checks.jsonl')
    if os.path.exists(cp):
        for l in open(cp, encoding='utf-8'):
            r = json.loads(l)
            chk[r['url']] = r

    pay = {}
    for f in glob.glob(os.path.join(GEN, 'payload-*.json')):
        d = json.load(open(f))
        pay['https://prokompressor.ru' + d['url']] = d

    n = 0
    index = []
    for r in inv:
        u = r['url']
        p = pay.get(u, {})
        k = keys.get(u, {})
        c = chk.get(u, {})
        b = {
            'url': u,
            'h1_stranicy': r['h1'],
            'title': r['title'],
            'description': r['description'],
            'statya_est': r['article_kind'] != 'none',
            'statya_tip': r['article_kind'],
            'statya_h2': r['h2'],
            'statya_znakov': r['article_chars'],
            'statya_tekst': plain(r.get('article_html', ''))[:12000],
            'ssylki_statyi': r['article_links'],
            'razdel': {
                'pozitsiy_v_vygruzke': p.get('count'),
                'tsena_min': p.get('price_min'),
                'tsena_max': p.get('price_max'),
                'primery_modeley': p.get('sample_models', [])[:12],
                'fasety_filtra': {kk: vv for kk, vv in sorted(r['facets'].items(), key=lambda x: -x[1])[:40]},
                'stranits_paginatsii': r['pagination_max'],
            },
            'fakty_brenda': (p.get('brand_facts') or '')[:FACTS_LIMIT],
            'spravka_kategorii': (p.get('category_reference') or '')[:REF_LIMIT],
            'klyuchi': {
                'Яндекс': k.get('Яндекс', {}).get('top', [])[:30],
                'Google': k.get('Google', {}).get('top', [])[:30],
                'itogi': {e: {kk: k.get(e, {}).get(kk) for kk in ('queries', 'shows', 'clicks', 'ctr', 'wpos')}
                          for e in ('Яндекс', 'Google')},
            },
            'kannibalizaciya': cann.get(u, [])[:12],
            'mehanicheskie_flagi': c.get('flags', []),
            'bitye_ssylki': c.get('links_bad', []),
        }
        s = slug_of(r['path'])
        json.dump(b, open(os.path.join(BRIEFS, s + '.json'), 'w'), ensure_ascii=False, indent=1)
        index.append({'slug': s, 'url': u, 'priority': c.get('priority', 3),
                      'shows': c.get('shows', 0), 'article_kind': r['article_kind'],
                      'flags': c.get('flags', [])})
        n += 1
    index.sort(key=lambda x: (x['priority'], -x['shows']))
    json.dump(index, open(os.path.join(HERE, 'briefs-index.json'), 'w'), ensure_ascii=False, indent=1)
    print('досье собрано:', n)
    import collections
    print('по приоритетам:', dict(sorted(collections.Counter(x['priority'] for x in index).items())))


if __name__ == '__main__':
    main()
