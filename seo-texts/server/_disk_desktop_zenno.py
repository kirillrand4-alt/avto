# -*- coding: utf-8 -*-
"""Что лежит на Рабочем столе (77 ГБ) и в zenno (51 ГБ)."""
import json
import os
import sys
import time

sys.stdout.reconfigure(encoding='utf-8')


def вес(п):
    и = 0
    try:
        for e in os.scandir(п):
            try:
                if e.is_symlink():
                    continue
                и += вес(e.path) if e.is_dir(follow_symlinks=False) \
                    else e.stat(follow_symlinks=False).st_size
            except (PermissionError, OSError):
                continue
    except (PermissionError, OSError):
        pass
    return и


def список(корень, n=10):
    д = {}
    try:
        for e in os.scandir(корень):
            try:
                д[e.name] = (вес(e.path) if e.is_dir(follow_symlinks=False)
                             else e.stat().st_size, e.is_dir(follow_symlinks=False))
            except (PermissionError, OSError):
                continue
    except (PermissionError, OSError):
        return []
    из = []
    for k, (v, папка) in sorted(д.items(), key=lambda x: -x[1][0])[:n]:
        if v < 200 * 2**20:
            break
        try:
            дата = time.strftime('%Y-%m-%d', time.localtime(
                os.path.getmtime(os.path.join(корень, k))))
        except OSError:
            дата = ''
        из.append([('DIR ' if папка else '') + k, round(v / 2**30, 1), дата])
    return из


итог = {}
for к in (r'C:\Users\Administrator\Desktop', r'C:\seostat\drop\zenno',
          r'C:\seostat\drop\drop-storage'):
    итог[к] = список(к)
# сколько файлов в очереди зенки и когда трогали
z = r'C:\seostat\drop\zenno'
try:
    итог['zenno_состав'] = {'элементов_в_корне': len(os.listdir(z))}
except OSError:
    pass
print(json.dumps(итог, ensure_ascii=False))
