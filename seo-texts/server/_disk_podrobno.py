# -*- coding: utf-8 -*-
"""Разложить три тяжёлых узла: Administrator, seostat\\drop, parser."""
import json
import os
import sys
import time

sys.stdout.reconfigure(encoding='utf-8')


def вес(путь):
    итого = 0
    try:
        с = list(os.scandir(путь))
    except (PermissionError, OSError):
        return 0
    for e in с:
        try:
            if e.is_symlink():
                continue
            итого += вес(e.path) if e.is_dir(follow_symlinks=False) \
                else e.stat(follow_symlinks=False).st_size
        except (PermissionError, OSError):
            continue
    return итого


def разложить(корень, сколько=8):
    д = {}
    try:
        for e in os.scandir(корень):
            try:
                д[e.name] = вес(e.path) if e.is_dir(follow_symlinks=False) \
                    else e.stat().st_size
            except (PermissionError, OSError):
                continue
    except (PermissionError, OSError):
        return []
    из = []
    for k, v in sorted(д.items(), key=lambda x: -x[1])[:сколько]:
        if v < 2**30 / 2:
            break
        п = os.path.join(корень, k)
        стар = ''
        try:
            стар = time.strftime('%Y-%m-%d', time.localtime(os.path.getmtime(п)))
        except OSError:
            pass
        из.append([k, round(v / 2**30, 1), стар])
    return из


итог = {}
for корень in (r'C:\Users\Administrator', r'C:\seostat\drop', r'C:\seostat\data',
               r'C:\parser', r'C:\sender'):
    итог[корень] = разложить(корень)
итог[r'C:\Users\Administrator\.ScreamingFrogSEOSpider'] = разложить(
    r'C:\Users\Administrator\.ScreamingFrogSEOSpider')
print(json.dumps(итог, ensure_ascii=False))
