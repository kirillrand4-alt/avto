import collections, json, os
K = r'C:\seostat\kc-proekty'
c = collections.Counter(); n = 0; размер = 0
for корень, _, ff in os.walk(K):
    for f in ff:
        n += 1
        размер += os.path.getsize(os.path.join(корень, f))
        fl = f.lower()
        if fl in ('thumbs.db', 'desktop.ini', '.ds_store') or fl.startswith('~$'):
            c[fl if not fl.startswith('~$') else '~$ (временные Office)'] += 1
print('===ИТОГ===')
print(json.dumps({'всего': n, 'служебные': dict(c), 'служебных': sum(c.values()), 'без_служебных': n - sum(c.values()),
                  'размер_ГБ': round(размер / 1e9, 2)}, ensure_ascii=False))
