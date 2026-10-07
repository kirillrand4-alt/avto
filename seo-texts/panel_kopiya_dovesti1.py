# -*- coding: utf-8 -*-
"""Доделать копию: junction на доказательства + проверка, что приложение импортируется.

Почему junction не встал с первого раза: обход каталога создавал пустую папку dokaz
(фильтр отсекал ФАЙЛЫ по полному пути, а имя каталога «dokaz» ему не мешало),
и mklink отказался — «файл уже существует». Пустую папку убираю и ставлю ссылку.
"""
import os, subprocess, sys

KOREN = r'C:\centro2'
ISTOK = r'C:\seostat'
OTN = os.path.join('static', 'centro', 'dokaz')
dst = os.path.join(KOREN, 'app', OTN)
src = os.path.join(ISTOK, 'app', OTN)

print('########## JUNCTION НА ДОКАЗАТЕЛЬСТВА')
if os.path.isdir(dst) and not os.path.islink(dst):
    vnutri = os.listdir(dst)
    print('  в копии папка есть, файлов внутри: %d' % len(vnutri))
    if not vnutri:
        os.rmdir(dst)
        print('  пустая — удалила')
    else:
        print('  НЕ пустая, ссылку ставить не буду')
if not os.path.exists(dst):
    r = subprocess.run(['cmd', '/c', 'mklink', '/J', dst, src],
                       capture_output=True, timeout=60)
    print('  mklink: %s' % (r.stdout + r.stderr).decode('cp866', 'replace').strip()[:100])
print('  теперь доказательств видно: %d' % (len(os.listdir(dst)) if os.path.isdir(dst) else 0))

print('\n########## ЧТО В КОПИИ')
for koren, kat, fajly in os.walk(os.path.join(KOREN, 'app')):
    if OTN in koren:
        kat[:] = []
        continue
    otn = os.path.relpath(koren, os.path.join(KOREN, 'app'))
    if otn.count(os.sep) < 1:
        print('  %-26s файлов %d' % (otn, len(fajly)))

print('\n########## ПРОВЕРКА ИМПОРТА (без запуска сервера)')
proba = os.path.join(KOREN, '_proba_import.py')
open(proba, 'w', encoding='utf-8').write(
    'import os, sys\n'
    'sys.path.insert(0, r"%s")\n' % KOREN +
    'os.chdir(r"%s")\n' % KOREN +
    'from app.services import centro_catalog as c, centro_sales as s\n'
    'print("centrifugal.db ->", c.db_path())\n'
    'print("centro_sales.db ->", s.sales_db_path())\n'
    'print("компаний в каталоге копии:", len(c.list_companies()))\n'
)
r = subprocess.run([r'C:\Program Files\Python311\python.exe', proba],
                   capture_output=True, timeout=180, cwd=KOREN)
print(r.stdout.decode('utf-8', 'replace')[-1500:])
err = r.stderr.decode('utf-8', 'replace')
if err.strip():
    print('  stderr: %s' % err[-900:])
