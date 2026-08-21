# -*- coding: utf-8 -*-
r"""Положить готовый файл в обменник: скопировать в каталог дропа.

Дроп раздаёт файлы из своего каталога; класть в него напрямую надёжнее, чем
гонять файл по HTTP через самого себя.
"""
import json
import os
import shutil

ЧТО = r'C:\sender\_tmp\bez-adresa-s-sayta.csv'
кандидаты = [os.environ.get('DROP_DIR') or '',
             r'C:\sender\server\drop-storage', r'C:\sender\drop-storage',
             r'C:\seostat\drop\drop-storage', r'C:\drop\drop-storage']
куда = ''
for п in кандидаты:
    if п and os.path.isdir(п):
        куда = п
        break
d = {'исходник': ЧТО, 'есть': os.path.exists(ЧТО),
     'байт': os.path.getsize(ЧТО) if os.path.exists(ЧТО) else 0}
if not куда:
    # найдём каталог дропа по работающему процессу
    for корень in (r'C:\sender', r'C:\seostat'):
        for путь, каталоги, _ф in os.walk(корень):
            if 'drop-storage' in каталоги:
                куда = os.path.join(путь, 'drop-storage')
                break
            каталоги[:] = [k for k in каталоги
                           if k not in ('node_modules', '_tmp', 'pagecache')]
        if куда:
            break
d['каталог_дропа'] = куда
if куда and os.path.exists(ЧТО):
    shutil.copy2(ЧТО, os.path.join(куда, os.path.basename(ЧТО)))
    d['положено'] = os.path.basename(ЧТО)
print(json.dumps(d, ensure_ascii=False, indent=1))
