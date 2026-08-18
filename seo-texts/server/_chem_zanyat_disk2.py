# -*- coding: utf-8 -*-
"""Каталоги по весу: полный результат в файл, в stdout — только таблица."""
import json
import os
import sys

sys.stdout.reconfigure(encoding='utf-8')
ВЫХОД = r'C:\sender\server\disk-zamer.json'


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


верх = {}
for e in os.scandir('C:\\'):
    try:
        if e.is_dir(follow_symlinks=False):
            верх[e.path] = вес(e.path)
    except (PermissionError, OSError):
        continue
топ = sorted(верх.items(), key=lambda x: -x[1])[:10]
подробно = {}
for путь, _ in топ[:4]:
    д = {}
    try:
        for e in os.scandir(путь):
            if e.is_dir(follow_symlinks=False):
                д[e.name] = вес(e.path)
    except (PermissionError, OSError):
        pass
    подробно[путь] = [[k, round(v / 2**30, 1)]
                      for k, v in sorted(д.items(), key=lambda x: -x[1])[:6]
                      if v > 2**30]
итог = {'верх': [[p, round(n / 2**30, 1)] for p, n in топ], 'подробно': подробно}
with open(ВЫХОД, 'w', encoding='utf-8') as f:
    json.dump(итог, f, ensure_ascii=False, indent=1)
    f.flush()
    os.fsync(f.fileno())
print(json.dumps(итог, ensure_ascii=False))
