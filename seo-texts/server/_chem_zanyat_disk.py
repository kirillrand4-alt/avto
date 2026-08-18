# -*- coding: utf-8 -*-
"""Чем занято место на диске: каталоги верхних уровней и самые тяжёлые файлы."""
import json
import os
import sys

sys.stdout.reconfigure(encoding='utf-8')
КОРЕНЬ = 'C:\\'
размеры, крупные = {}, []


def обойти(путь, верх):
    """Размер поддерева; попутно копим файлы тяжелее 300 МБ."""
    итого = 0
    try:
        с = list(os.scandir(путь))
    except (PermissionError, OSError):
        return 0
    for e in с:
        try:
            if e.is_symlink():
                continue
            if e.is_dir(follow_symlinks=False):
                итого += обойти(e.path, верх)
            else:
                n = e.stat(follow_symlinks=False).st_size
                итого += n
                if n > 300 * 2**20:
                    крупные.append((n, e.path))
        except (PermissionError, OSError):
            continue
    return итого


for e in os.scandir(КОРЕНЬ):
    try:
        if e.is_dir(follow_symlinks=False):
            размеры[e.path] = обойти(e.path, e.path)
    except (PermissionError, OSError):
        continue

топ = sorted(размеры.items(), key=lambda x: -x[1])[:12]
# внутри самого тяжёлого — разложить на подкаталоги
детали = {}
if топ:
    гл = топ[0][0]
    д = {}
    try:
        for e in os.scandir(гл):
            if e.is_dir(follow_symlinks=False):
                д[e.path] = обойти(e.path, e.path)
    except (PermissionError, OSError):
        pass
    детали[гл] = [{'путь': p, 'ГБ': round(n / 2**30, 1)}
                  for p, n in sorted(д.items(), key=lambda x: -x[1])[:10]]

итог = {'по_каталогам_ГБ': [{'путь': p, 'ГБ': round(n / 2**30, 1)} for p, n in топ],
        'внутри_самого_тяжёлого': детали,
        'файлы_крупнее_300МБ': [{'ГБ': round(n / 2**30, 2), 'путь': p}
                                for n, p in sorted(крупные, reverse=True)[:15]]}
import shutil
u = shutil.disk_usage(КОРЕНЬ)
итог['диск'] = {'всего_ГБ': round(u.total / 2**30), 'занято_ГБ': round(u.used / 2**30),
                'свободно_ГБ': round(u.free / 2**30)}
print(json.dumps(итог, ensure_ascii=False, indent=1))
