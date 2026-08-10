# -*- coding: utf-8 -*-
"""Отпечатки развёрнутых шаблонов панели — чтобы правку мог проверить не только я.

3-я сессия справедливо сказала: моё «страница отдала 158 475 знаков» проверить нечем,
потому что снято ИЗНУТРИ контейнера из-под входа. Отпечаток файла на сервере проверяется
любым, у кого есть доступ к серверу, и не требует пароля владельца.
"""
import hashlib, json, os, re

o = {}
for imya in ('centro.html', 'park.html', 'park_card.html', 'spisok.html'):
    p = os.path.join(r'C:\seostat\app\templates', imya)
    if not os.path.exists(p):
        o[imya] = 'нет файла'
        continue
    b = open(p, 'rb').read()
    t = b.decode('utf-8', 'replace')
    o[imya] = {'байт': len(b), 'sha256': hashlib.sha256(b).hexdigest()[:16],
               'ссылка на список': '/centro/spisok' in t,
               'ссылка на парк': '/centro/park' in t}
o['snimkov_dokazatelstv'] = len(os.listdir(r'C:\seostat\app\static\centro\dokaz')) \
    if os.path.isdir(r'C:\seostat\app\static\centro\dokaz') else 0
print(json.dumps(o, ensure_ascii=False, indent=1))
