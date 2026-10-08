import sys, re, collections, pandas as pd
x = pd.ExcelFile(sys.argv[1])
k = x.parse('Компании', dtype={'ИНН': str}); c = x.parse('Контакты', dtype={'ИНН': str})
k['ИНН'] = k['ИНН'].str.strip(); c['ИНН'] = c['ИНН'].str.strip()
c['cif'] = c['Мобильный'].fillna(c['Рабочий']).astype(str).str.replace(r'\D', '', regex=True).str[-10:]
po_nom = c.groupby('cif')['ИНН'].apply(lambda s: sorted(set(s)))
obsh = po_nom[po_nom.apply(len) > 1]
print('номеров, общих для нескольких ИНН:', len(obsh), '; размеры:', collections.Counter(obsh.apply(len)).most_common())
for nom, inns in obsh[obsh.apply(len) >= 4].items():
    print('  ', nom, len(inns), c[c['cif'] == nom]['Роль'].value_counts().to_dict(), k[k['ИНН'].isin(inns)]['Название'].tolist()[:6])
def norm(h):
    h = str(h or '').lower()
    h = re.sub(r'\(.*?\)', ' ', h)
    h = re.sub(r'\b(ооо|ао|пао|зао|оао|гк|группа компаний|холдинг|агрохолдинг)\b', ' ', h)
    h = re.sub(r'[«»"\'“”„.,]', ' ', h)
    return ' '.join(h.split())
k['h'] = k['Холдинг (агент)'].map(lambda v: norm(v) if pd.notna(v) else '')
print('\nхолдингов по названию (с ≥2 ИНН):', (k[k['h'] != ''].groupby('h').size() > 1).sum())
print(k[k['h'] != ''].groupby('h').size().sort_values(ascending=False).head(8).to_dict())
# union-find
par = {}
def f(a):
    par.setdefault(a, a)
    while par[a] != a:
        par[a] = par[par[a]]; a = par[a]
    return a
def u(a, b): par[f(a)] = f(b)
for inns in obsh: 
    for i in inns[1:]: u(inns[0], i)
for h, g in k[k['h'] != ''].groupby('h'):
    l = g['ИНН'].tolist()
    for i in l[1:]: u(l[0], i)
gr = collections.defaultdict(list)
for i in k['ИНН']: gr[f(i)].append(i)
bol = {r: m for r, m in gr.items() if len(m) > 1}
print('\nгрупп (≥2 ИНН):', len(bol), 'размеры:', collections.Counter(len(m) for m in bol.values()).most_common())
for r, m in sorted(bol.items(), key=lambda p: -len(p[1]))[:6]:
    print('  ', len(m), k[k['ИНН'].isin(m)]['Название'].tolist()[:8], '| холдинг:', set(k[k['ИНН'].isin(m)]['Холдинг (агент)'].dropna()))
