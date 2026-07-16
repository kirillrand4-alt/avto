# -*- coding: utf-8 -*-
import csv, sys, re, json
from collections import Counter
csv.field_size_limit(10**9)

BRANDS = {  # slug -> варианты написания производителя/в названии
 'airbox': ['airbox'], 'ariacom': ['ariacom'], 'atlas-copco': ['atlas copco'],
 'atmos': ['atmos'], 'aztec': ['aztec'], 'bezhetsk': ['бежецк'],
 'comprag': ['comprag'], 'cross-air': ['cross air','cross-air'], 'dalgakiran': ['dalgakiran'],
 'dali': ['dali'], 'das': ['das'], 'enger': ['enger'], 'et-compressors': ['et compressors','et-compressors','et сompressors'],
 'kraftmachine': ['kraftmachine'], 'magnus': ['magnus'], 'master-blast-': ['master blast'],
 'minskiy-motornyy-zavod': ['минский моторный','ммз'], 'ozen': ['ozen'], 'remeza': ['remeza'],
 'zega': ['zega'], 'zif': ['зиф'],
}

f = open('bitrix/export_file_2ov3pw9ju90trsle.csv', encoding='utf-8-sig', newline='')
rdr = csv.reader(f, delimiter=';')
header = next(rdr)
ix = {c: i for i, c in enumerate(header)}
COLS = {'name':'IE_NAME','active':'IE_ACTIVE','power':'IP_PROP22562','perf':'IP_PROP22571',
'pressure':'IP_PROP22573','block':'IP_PROP23168','eng_brand':'IP_PROP23000','eng_model':'IP_PROP23013',
'fuel':'IP_PROP22677','tank':'IP_PROP22662','tank2':'IP_PROP23004','series2':'IP_PROP22576',
'manuf':'IP_PROP22553','country':'IP_PROP23191','mobile':'IP_PROP22566','warranty':'IP_PROP23188','type':'IP_PROP22580'}
C = {k: ix[v] for k, v in COLS.items()}

agg = {s: {} for s in BRANDS}
for row in rdr:
    if len(row) < len(header): row += ['']*(len(header)-len(row))
    name = row[C['name']].strip()
    lown = name.lower()
    if 'дизель' not in lown and 'дизель' not in row[C['type']].lower(): continue
    manuf = row[C['manuf']].strip().lower()
    for slug, keys in BRANDS.items():
        if any(k in lown or k == manuf or k in manuf for k in keys):
            d = agg[slug].setdefault(row[2], {k: set() for k in C})
            for k, i in C.items():
                v = row[i].strip()
                if v: d[k].add(v)
            break

result = {}
for slug, prods in agg.items():
    if not prods: result[slug] = {'count': 0}; continue
    def rng(key):
        vals = []
        for d in prods.values():
            for v in d[key]:
                try: vals.append(float(v.replace(',','.')))
                except: pass
        return [min(vals), max(vals)] if vals else None
    r = {'count': len(prods),
         'power': rng('power'), 'perf': rng('perf'), 'pressure': rng('pressure'),
         'fuel': rng('fuel'), 'tank': rng('tank') or rng('tank2'),
         'blocks': dict(Counter(v for d in prods.values() for v in d['block']).most_common(5)),
         'engines': dict(Counter(v for d in prods.values() for v in d['eng_brand']).most_common(6)),
         'eng_models': dict(Counter(v for d in prods.values() for v in d['eng_model']).most_common(5)),
         'series': dict(Counter(v for d in prods.values() for v in d['series2']).most_common(6)),
         'warranty': dict(Counter(v for d in prods.values() for v in d['warranty']).most_common(4)),
         'country': dict(Counter(v for d in prods.values() for v in d['country']).most_common(3)),
         'mobile': dict(Counter(v for d in prods.values() for v in d['mobile']).most_common(3)),
        }
    # серии из названий
    sers = Counter()
    for pid, d in prods.items():
        for n in d['name']:
            m = re.search(r'\b(LUY|DC|DACS|XAS|XAHS|XATS|XAVS|XAMS|Borey|БОРЕЙ|DLCY|DLZJ|ПКСД|ПВ|ДК|MB|ДЭН)[- ]?\d', n, re.I)
            if m: sers[m.group(1).upper()] += 1
    r['name_series'] = dict(sers.most_common(6))
    result[slug] = r

json.dump(result, open('diz-brands-aggregates.json','w'), ensure_ascii=False, indent=1)
for slug, r in result.items():
    if r['count']:
        print(f"{slug:<24} n={r['count']:<4} мощн={r['power']} произв={r['perf']} давл={r['pressure']} блоки={list(r['blocks'])[:2]} двиг={list(r['engines'])[:3]} серии={list(r['name_series'])[:3]}")
    else:
        print(f"{slug:<24} НЕТ В ВЫГРУЗКЕ")
