# -*- coding: utf-8 -*-
r"""Наложения фронта — в дроп, чтобы лежали в репозитории, а не только на сервере.

`sobrat_front.py` кладёт поверх восстановленных исходников файлы из
web-pravki. Живут они на сервере, и любая потеря сервера или песочницы стоила
бы всех правок панели. Пакуем без .gz-выгрузок — это артефакты, не исходники.
"""
import json
import os
import shutil
import tarfile

ПРАВКИ = r'C:\sender\_tmp\web-pravki'
АРХИВ = r'C:\sender\_tmp\web-pravki.tar.gz'
ДРОП = r'C:\seostat\drop\drop-storage'

файлы = []
with tarfile.open(АРХИВ, 'w:gz') as t:
    for путь, _к, имена in os.walk(ПРАВКИ):
        for и in имена:
            if и.endswith('.gz'):
                continue
            п = os.path.join(путь, и)
            отн = os.path.relpath(п, ПРАВКИ).replace(os.sep, '/')
            t.add(п, arcname=отн)
            файлы.append({'файл': отн, 'байт': os.path.getsize(п)})
shutil.copy2(АРХИВ, os.path.join(ДРОП, os.path.basename(АРХИВ)))
print(json.dumps({'файлов': len(файлы), 'состав': файлы,
                  'архив': АРХИВ, 'байт': os.path.getsize(АРХИВ)},
                 ensure_ascii=False, indent=1))
