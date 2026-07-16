# -*- coding: utf-8 -*-
import csv, sys, re, json
from collections import Counter
csv.field_size_limit(10**9)

models = json.load(open('diz-brands-models.json'))
name2slug = {}
for slug, lst in models.items():
    for n in lst:
        name2slug[n] = slug

f = open('bitrix/export_file_2ov3pw9ju90trsle.csv', encoding='utf-8-sig', newline='')
rdr = csv.reader(f, delimiter=';')
header = next(rdr)
ix = {c: i for i, c in enumerate(header)}
COLS = {'name':'IE_NAME','power':'IP_PROP22562','perf':'IP_PROP22571','pressure':'IP_PROP22573',
'block':'IP_PROP23168','eng_brand':'IP_PROP23000','eng_model':'IP_PROP23013','fuel':'IP_PROP22677',
'tank':'IP_PROP22662','tank2':'IP_PROP23004','series2':'IP_PROP22576','country':'IP_PROP23191',
'mobile':'IP_PROP22566','warranty':'IP_PROP23188'}
C = {k: ix[v] for k, v in COLS.items()}

data = {}
matched = set()
for row in rdr:
    if len(row) < len(header): row += ['']*(len(header)-len(row))
    n = row[C['name']].strip()
    slug = name2slug.get(n)
    if not slug: continue
    matched.add(n)
    d = data.setdefault(slug, {}).setdefault(n, {k: set() for k in C})
    for k, i in C.items():
        v = row[i].strip()
        if v: d[k].add(v)

result = {}
for slug, prods in data.items():
    # исключаем бензиновые из подсчётов
    diesel = {n: d for n, d in prods.items() if 'бензин' not in n.lower()}
    def rng(key):
        vals = []
        for d in diesel.values():
            for v in d[key]:
                try: vals.append(float(v.replace(',','.')))
                except: pass
        return [min(vals), max(vals)] if vals else None
    def top(key, n=6):
        return dict(Counter(v for d in diesel.values() for v in d[key]).most_common(n))
    sers = Counter()
    for nm in diesel:
        m = re.search(r'\b(LUY|DC|DACS|XAS|XAHS|XATS|XAVS|XAMS|Borey|БОРЕЙ|DLCY|DLZJ|ПКСД|ПВ|ДК|MB|SDO|SAX|AC\d|ADS|OPC|PDH|PDC|SPDB|DPK|BVK|DVK|ET SD|АСО|KMD|KD)[- ]?\d?', nm, re.I)
        if m: sers[re.sub(r'\d$','',m.group(1).upper()).strip()] += 1
    result[slug] = {
        'total_in_tag': len(models[slug]),
        'diesel_count': len(diesel),
        'benzin_in_tag': len(models[slug]) - len([n for n in models[slug] if 'бензин' not in n.lower()]),
        'matched_in_export': len(prods),
        'power': rng('power'), 'perf': rng('perf'), 'pressure': rng('pressure'),
        'fuel': rng('fuel'), 'tank': rng('tank') or rng('tank2'),
        'blocks': top('block'), 'engines': top('eng_brand'), 'eng_models': top('eng_model',4),
        'series_prop': top('series2'), 'series_names': dict(sers.most_common(6)),
        'warranty': top('warranty',4), 'country': top('country',3), 'mobile': top('mobile',3),
        'sample_models': sorted(diesel)[:8],
    }
json.dump(result, open('diz-brands-aggregates2.json','w'), ensure_ascii=False, indent=1)
print(f'сматчено имён: {len(matched)} из {len(name2slug)}', file=sys.stderr)
for slug, r in sorted(result.items()):
    print(f"{slug:<24} тег={r['total_in_tag']:<4} диз={r['diesel_count']:<4} матч={r['matched_in_export']:<4} мощн={r['power']} давл={r['pressure']} блоки={list(r['blocks'])[:2]} двиг={list(r['engines'])[:3]}", file=sys.stderr)
