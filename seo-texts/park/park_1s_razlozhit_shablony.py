# -*- coding: utf-8 -*-
"""Раскладывает шаблоны парка из C:\\sender\\_ops в C:\\seostat\\app\\templates.

С копией перед заменой: шаблон, который на сервере уже работает, ценнее моего нового,
пока новый не проверен пробой. Возврат — переименованием .bak-<время> обратно.
"""
import os, shutil, time, json

IST = r'C:\sender\_ops'
CEL = r'C:\seostat\app\templates'
o = {'polozheno': [], 'kopii': [], 'oshibki': []}
for imya in ('park.html', 'park_card.html', 'spisok.html'):
    src = os.path.join(IST, imya)
    dst = os.path.join(CEL, imya)
    if not os.path.exists(src):
        o['oshibki'].append('нет исходника: ' + src)
        continue
    try:
        if os.path.exists(dst):
            bak = dst + '.bak-%d' % int(time.time())
            shutil.copyfile(dst, bak)
            o['kopii'].append(os.path.basename(bak))
        shutil.copyfile(src, dst)
        o['polozheno'].append('%s (%d б)' % (imya, os.path.getsize(dst)))
    except Exception as e:
        o['oshibki'].append('%s: %s' % (imya, e))
print(json.dumps(o, ensure_ascii=False, indent=1))
