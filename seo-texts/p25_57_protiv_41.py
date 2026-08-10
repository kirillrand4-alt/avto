# -*- coding: utf-8 -*-
"""57 строк «контактное лицо» в списке против 41 по мерке: смотрю КАЖДУЮ, а не спорю числами."""
import io, json, os, re, collections
OPS = r'C:\sender\_ops'
mash = set()
for p in ('park_ingest_3.jsonl','park_ingest_3b.jsonl','park_ingest_3c.jsonl'):
    q = os.path.join(OPS,p)
    if os.path.exists(q):
        for s in io.open(q,encoding='utf-8'):
            try: o=json.loads(s)
            except Exception: continue
            if o.get('inn'): mash.add(o['inn'])
kont = collections.defaultdict(list)
for s in io.open(os.path.join(OPS,'PARK-EIS-KONTAKTNOE-LICO-3S.jsonl'),encoding='utf-8'):
    try: o=json.loads(s)
    except Exception: continue
    n = re.sub(r'\D','',o.get('telefon') or '')
    if o.get('inn'): kont[(o['inn'], n[-10:] if len(n)>=10 else n)].append(o)
sh=None; ish=collections.Counter(); primery=[]
for s in io.open(os.path.join(OPS,'PARK-SPISOK-DLYA-ZVONKA-3S.csv'),encoding='utf-8-sig'):
    p=s.rstrip('\n').split(';')
    if sh is None: sh=p; continue
    if len(p)!=len(sh): ish['строка CSV с лишней точкой с запятой']+=1; continue
    o=dict(zip(sh,p))
    if not o.get('dolzhnost','').startswith('контактное лицо'): continue
    n=re.sub(r'\D','',o.get('nomer',''))[-10:]
    k=(o['inn'],n)
    if o['inn'] not in mash: ish['В СПИСКЕ, НО МАШИНА НЕ ДОКАЗАНА']+=1; primery.append(('машины нет',o['inn'],o.get('chelovek','')[:22]))
    elif k in kont: ish['есть в потоке контактных лиц, машина доказана']+=1
    else: ish['машина доказана, но такой пары ИНН+номер в потоке нет']+=1; primery.append(('пары нет',o['inn'],o.get('nomer','')))
print('\n\n########## ПРИМЕРЫ РАСХОЖДЕНИЙ')
for x in primery[:12]: print('   %-12s %-12s %s' % x)
print('\n########## ЧИСЛА')
for k,v in ish.most_common(): print('   %-52s %5d' % (k[:52],v))
print('ИТОГ ' + json.dumps(dict(ish), ensure_ascii=False))
