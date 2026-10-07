# -*- coding: utf-8 -*-
"""Копия на venv боевого сервера + проверка импорта и путей к базам.

venv не дублирую: это интерпретатор с пакетами, а не код приложения. Копии нужен свой
КОД и свои БАЗЫ, а bcrypt у обеих один и тот же. Дубль venv — это ещё сотни мегабайт
и вторая точка, где надо помнить про обновление пакетов.
"""
import io, os, subprocess

KOREN = r'C:\centro2'
VENV = r'C:\seostat\.venv\Scripts\python.exe'
OTN = os.path.join('static', 'centro', 'dokaz')
dst = os.path.join(KOREN, 'app', OTN)

print('########## JUNCTION')
print('  есть каталог доказательств в копии: %s' % os.path.isdir(dst))
if os.path.isdir(dst):
    try:
        print('  файлов видно через ссылку: %d' % len(os.listdir(dst)))
    except Exception as e:
        print('  не прочитался: %s' % str(e)[:60])

print('\n########## ПРОВЕРКА НА VENV')
proba = os.path.join(KOREN, '_proba_import.py')
io.open(proba, 'w', encoding='utf-8').write(
    'import os, sys\n'
    'from app.services import centro_catalog as c, centro_sales as s\n'
    'print("CENTRIFUGAL_DB ->", c.db_path())\n'
    'print("CENTRO_SALES_DB ->", s.sales_db_path())\n'
    'print("компаний в каталоге копии:", len(c.list_companies()))\n'
    'import sqlite3\n'
    'conn = sqlite3.connect(str(s.sales_db_path()))\n'
    'print("пользователей:", conn.execute("select count(*) from users").fetchone()[0])\n'
    'print("назначений:", conn.execute("select count(*) from company_assignment").fetchone()[0])\n'
)
r = subprocess.run([VENV, '_proba_import.py'], capture_output=True, timeout=300, cwd=KOREN)
print(r.stdout.decode('utf-8', 'replace')[-1200:])
e = r.stderr.decode('utf-8', 'replace')
if e.strip():
    print('  stderr: %s' % e[-700:])

print('\n########## ПРАВЛЮ ЗАПУСКАЛКУ НА VENV')
bat = os.path.join(KOREN, 'start-centro2.bat')
io.open(bat, 'w', encoding='utf-8').write(
    '@echo off\r\n'
    'rem Копия панели обзвона. Боевая на 8012, эта на 8016.\r\n'
    'rem venv общий с боевой: там пакеты (bcrypt, fastapi), а код и базы у копии свои.\r\n'
    'cd /d C:\\centro2\r\n'
    '"C:\\seostat\\.venv\\Scripts\\python.exe" -m uvicorn app.obzvon:app '
    '--host 127.0.0.1 --port 8016\r\n')
print('  %s переписан на venv' % bat)
