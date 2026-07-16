# -*- coding: utf-8 -*-
"""Группировка всех фактов по брендам из всех источников — локально, для последующего синтеза."""
import json, glob, os, re

# канонический список брендов (по брендовым страницам)
brand_facts = {x['_slug']: x for x in json.load(open('kb/brand-pages-facts.json'))}
manuf = {x['_slug']: x for x in json.load(open('kb/manuf-facts.json'))}
price_c = json.load(open('katalogi/kb-enrichment.json'))
price_r = json.load(open('katalogi/kb-enrichment-rest.json'))
websearch = open('kb/web-search-facts.md').read()

def norm(s):
    if isinstance(s,(list,tuple)): s=' '.join(str(x) for x in s)
    return re.sub(r'[^a-zа-я0-9]','', str(s or '').lower())

# сопоставление slug -> варианты имени для матчинга листов прайса
brands = {}
for slug, bf in brand_facts.items():
    name = bf.get('brand') or slug
    brands[slug] = {'slug': slug, 'name': name, 'norm': norm(slug.replace('_',''))}

def price_for(slug, name):
    keys = {norm(slug.replace('_','')), norm(name)}
    hits = []
    for rec in price_c + price_r:
        sheet = rec.get('_sheet','')
        rb = rec.get('brand','')
        if any(k and (k in norm(sheet) or k in norm(rb)) for k in keys if len(k)>3):
            hits.append({'sheet': sheet, 'series': rec.get('series'), 'marking': rec.get('marking_rules'),
                         'deps': rec.get('dependencies'), 'ranges': rec.get('ranges'),
                         'blocks': rec.get('blocks_engines'), 'type': rec.get('product_type')})
    return hits[:6]

def dossier(slug):
    for cand in [f'kb/brand-{slug}.md', f'kb/brand-{slug.replace("_","-")}.md']:
        if os.path.exists(cand): return open(cand).read()[:2500]
    return ''

def websec(name, slug):
    for key in [name, slug, slug.replace('_',' ')]:
        m = re.search(rf'##[^\n]*{re.escape(key)}[^\n]*\n(.*?)(?=\n##|\Z)', websearch, re.S|re.I)
        if m: return m.group(0)[:900]
    return ''

out = {}
for slug, b in brands.items():
    out[slug] = {
        'slug': slug, 'name': b['name'],
        'brand_page': brand_facts.get(slug, {}).get('from_page'),
        'manuf_site': {k: manuf[slug].get(k) for k in ('country','founded','product_types','key_technologies','series_mentioned','claims')} if slug in manuf else None,
        'price_sheets': price_for(slug, b['name']),
        'dossier_excerpt': dossier(slug),
        'websearch': websec(b['name'], slug),
    }
json.dump(out, open('kb/brands-assembled.json','w'), ensure_ascii=False, indent=1)
withprice = sum(1 for v in out.values() if v['price_sheets'])
withmanuf = sum(1 for v in out.values() if v['manuf_site'])
withweb = sum(1 for v in out.values() if v['websearch'])
print(f'брендов собрано: {len(out)} | с прайсом: {withprice} | с сайтом произв.: {withmanuf} | с веб-поиском: {withweb}')
