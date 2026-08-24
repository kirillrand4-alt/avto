# -*- coding: utf-8 -*-
"""Где ещё лежат скачанные страницы: каталоги дропа, зенка, карантин."""
import json
import os

BAZY = [r'C:\seostat\drop', r'C:\seostat\drop\zenno', r'C:\sender\_tmp',
        r'C:\seostat\drop\pagecache_otkloneno', r'C:\seostat\drop\drop-storage']
for b in BAZY:
    try:
        n = os.listdir(b)
    except Exception as e:  # noqa: BLE001
        print(b, '-> нет:', str(e)[:60])
        continue
    kat = [x for x in n if os.path.isdir(os.path.join(b, x))]
    fl = [x for x in n if not os.path.isdir(os.path.join(b, x))]
    ras = {}
    for x in fl:
        e = os.path.splitext(x)[1].lower()
        ras[e] = ras.get(e, 0) + 1
    print(b, '| файлов', len(fl), '| каталогов', len(kat))
    print('   расширения:', json.dumps(dict(sorted(ras.items(), key=lambda i: -i[1])[:8]),
                                       ensure_ascii=False))
    print('   каталоги:', json.dumps(kat[:25], ensure_ascii=False)[:600])
    print('   примеры файлов:', json.dumps(fl[:6], ensure_ascii=False)[:400])

# подкаталоги zenno
z = r'C:\seostat\drop\zenno'
if os.path.isdir(z):
    for x in os.listdir(z)[:12]:
        p = os.path.join(z, x)
        if os.path.isdir(p):
            try:
                nn = os.listdir(p)
                print('  zenno/%s: %d файлов, примеры %s' % (x, len(nn),
                                                             json.dumps(nn[:4], ensure_ascii=False)[:200]))
            except Exception as e:  # noqa: BLE001
                print('  zenno/%s: %s' % (x, str(e)[:60]))
