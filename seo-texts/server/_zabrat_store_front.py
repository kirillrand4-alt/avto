# -*- coding: utf-8 -*-
r"""Забрать в дроп изменённые файлы: store.py и наложение Leads.tsx."""
import json
import os
import shutil
import tarfile

ФАЙЛЫ = [(r'C:\sender\sender\store.py', 'store.py'),
         (r'C:\sender\_tmp\web-pravki\screens\Leads.tsx', 'Leads.tsx')]
АРХИВ = r'C:\sender\_tmp\bitrix-pravka.tar.gz'
ДРОП = r'C:\seostat\drop\drop-storage'
состав = []
with tarfile.open(АРХИВ, 'w:gz') as t:
    for п, имя in ФАЙЛЫ:
        if os.path.exists(п):
            t.add(п, arcname=имя)
            состав.append({'файл': имя, 'байт': os.path.getsize(п)})
shutil.copy2(АРХИВ, os.path.join(ДРОП, os.path.basename(АРХИВ)))
print(json.dumps({'состав': состав}, ensure_ascii=False, indent=1))
