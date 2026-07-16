# -*- coding: utf-8 -*-
"""Сборка answer-kb.json - компактная база для ответов на письма:
бренды (модели/серии/гарантии/claims), ценовые медианы, проекты по отраслям."""
import json, os, collections

ST = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

kp = json.load(open(os.path.join(ST, 'kb', 'kp-base-all.json')))
brands = {}
for b, v in kp.items():
    models = v.get('models', {})
    if not models and not v.get('company_claims'):
        continue
    brands[b] = dict(
        n_models=len(models),
        series=sorted(v.get('series', {}), key=lambda s: -v['series'][s])[:8],
        warranties=list(v.get('warranties', {}))[:3],
        claims=list(v.get('company_claims', {}))[:5],
        screw_blocks=list(v.get('screw_blocks', {}))[:4],
        models_sample={m: d for m, d in list(models.items())[:12]})

bx = json.load(open(os.path.join(ST, 'frog', 'bitrix-prices.json')))
prices = dict(by_cat={k: v for k, v in bx['by_cat'].items() if v['n'] >= 10},
              by_brand={k.split(' | ')[0]: v for k, v in bx['by_brand_cat'].items()
                        if k.endswith('| Воздушные компрессоры') and v['n'] >= 20})

proj = json.load(open(os.path.join(ST, 'projects-index.json')))
by_sphere = collections.defaultdict(list)
for p in proj:
    s = (p.get('sphere') or p.get('category') or 'прочее').strip()
    if len(by_sphere[s]) < 6:
        by_sphere[s].append(dict(title=p.get('h1', '')[:90], url=p.get('url'),
                                 date=p.get('date', '')))
spheres = {s: v for s, v in by_sphere.items()}

out = dict(brands=brands, prices=prices, projects_by_sphere=spheres,
           company=dict(name='ООО «Руспром»', site='prokompressor.ru',
                        experience='5580+ проектов подбора', brands_own=['Enger'],
                        brands_friendly=['Berg', 'Cross Air', 'Dali', 'Hansmann']))
json.dump(out, open(os.path.join(os.path.dirname(__file__), 'answer-kb.json'), 'w'),
          ensure_ascii=False, indent=1)
print('answer-kb: брендов', len(brands), '| отраслей', len(spheres),
      '| размер', os.path.getsize(os.path.join(os.path.dirname(__file__), 'answer-kb.json'))//1000, 'кб')
