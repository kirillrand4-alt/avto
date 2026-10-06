import os, json, collections
D = os.path.dirname(os.path.abspath(__file__))
L = sorted((x for x in os.listdir(D) if x.startswith('pusk-kat')), key=lambda x: os.path.getmtime(os.path.join(D, x)))
print('===ИТОГ===')
print(L[-1:], open(os.path.join(D, L[-1]), encoding='utf-8', errors='replace').read()[-1500:])
c = collections.Counter(json.loads(l)['source'] for l in open(os.path.join(D, 'KATALOGI.jsonl'), encoding='utf-8'))
print(c)
