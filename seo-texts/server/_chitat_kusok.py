# -*- coding: utf-8 -*-
r"""Показать куски серверных файлов: маршрут очереди подтверждения."""
import os

КУСКИ = [(r'C:\sender\sender\api\app.py', 899, 62)]
out = []
for п, начало, сколько in КУСКИ:
    if not os.path.exists(п):
        out.append('НЕТ ФАЙЛА %s' % п)
        continue
    with open(п, encoding='utf-8', errors='replace') as f:
        строки = f.readlines()
    out.append('=== %s : %d ===' % (os.path.basename(п), начало))
    for i in range(начало - 1, min(len(строки), начало - 1 + сколько)):
        out.append('%4d %s' % (i + 1, строки[i].rstrip()[:150]))
print('\n'.join(out))
