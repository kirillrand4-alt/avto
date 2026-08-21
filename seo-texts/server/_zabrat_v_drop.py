# -*- coding: utf-8 -*-
r"""Забрать серверные модули в дроп — чтобы правились в репозитории, а не вслепую.

Откат песочницы уже стирал эти файлы из рабочего дерева; на сервере они живут
в единственном экземпляре. Кладём копию в обменник и оттуда — в репозиторий.
"""
import json
import os
import shutil
import tarfile

ФАЙЛЫ = [r'C:\sender\sender\lid_ssylka.py', r'C:\sender\sender\lid_stranica.py']
АРХИВ = r'C:\sender\_tmp\lid-moduli.tar.gz'
ДРОП = r'C:\seostat\drop\drop-storage'
состав = []
with tarfile.open(АРХИВ, 'w:gz') as t:
    for п in ФАЙЛЫ:
        if not os.path.exists(п):
            состав.append({'НЕТ': п})
            continue
        t.add(п, arcname=os.path.basename(п))
        состав.append({'файл': os.path.basename(п), 'байт': os.path.getsize(п)})
shutil.copy2(АРХИВ, os.path.join(ДРОП, os.path.basename(АРХИВ)))
print(json.dumps({'состав': состав, 'архив': АРХИВ}, ensure_ascii=False, indent=1))
