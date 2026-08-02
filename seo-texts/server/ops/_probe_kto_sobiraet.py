# -*- coding: utf-8 -*-
"""Кто и чем собирает centrifugal.db — ответ файлами, а не догадкой."""
import glob
import os
import sys

sys.path.insert(0, r'C:\seostat')
from app.services import centro_catalog  # noqa: E402


def main():
    п = str(centro_catalog.db_path())
    print(f'база панели: {п}')
    if os.path.exists(п):
        import time
        print(f'  размер {os.path.getsize(п)} байт, изменена '
              f'{time.strftime("%Y-%m-%d %H:%M", time.localtime(os.path.getmtime(п)))}')
    with centro_catalog.connect() as conn:
        for k, v in conn.execute('SELECT key, value FROM import_info').fetchall():
            print(f'  import_info: {k} = {str(v)[:80]}')
        print('  источники строк person (топ):')
        for s, n in conn.execute(
                'SELECT COALESCE(source,\'\'), COUNT(*) FROM person '
                'GROUP BY source ORDER BY 2 DESC LIMIT 8').fetchall():
            print(f'    {n:>5}  {s[:70]}')

    print('\nскрипты, которые пишут centrifugal.db:')
    for корень in (r'C:\seostat', r'C:\sender', r'C:\seostat\drop\drop-storage'):
        for f in glob.glob(os.path.join(корень, '**', '*.py'), recursive=True):
            if '__pycache__' in f:
                continue
            try:
                т = open(f, encoding='utf-8', errors='replace').read()
            except Exception:  # noqa: BLE001
                continue
            if 'centrifugal.db' in т and ('CREATE TABLE' in т or 'INSERT INTO' in т):
                import time
                print(f'  {os.path.getsize(f):>8}  '
                      f'{time.strftime("%m-%d %H:%M", time.localtime(os.path.getmtime(f)))}  {f}')


if __name__ == '__main__':
    main()
