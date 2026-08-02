# -*- coding: utf-8 -*-
"""Разведка панели обзвона: где её код, чем она рисует карточку.

Владелец просит пять правок в интерфейсе (`/obzvon/centro/`), а править
надо ИМЕННО ту панель, что он видит. Служба зовётся `obzvon`, порт 8012 —
значит у неё свой каталог, не `enrich_panel`. Ищем его и смотрим состав.
"""
import glob
import os
import subprocess

NSSM = 'C:\\nssm.exe'


def main():
    # где лежит служба
    for пар in ('Application', 'AppDirectory', 'AppParameters'):
        try:
            r = subprocess.run([NSSM, 'get', 'obzvon', пар],
                               capture_output=True, timeout=60)
            raw = (r.stdout or b'') + (r.stderr or b'')
            try:
                txt = raw.decode('utf-16-le')
            except Exception:  # noqa: BLE001
                txt = raw.decode('utf-8', 'replace')
            print(f'{пар}: {txt.replace(chr(0), "").strip()[:200]}')
        except Exception as e:  # noqa: BLE001
            print(f'{пар}: ошибка {str(e)[:80]}')

    # точка входа панели обзвона
    print('\n=== app/obzvon.py ===')
    print(open(r'C:\seostat\app\obzvon.py', encoding='utf-8',
               errors='replace').read())
    # где шаблоны карточки
    print('\n=== шаблоны, где упоминается centro/обзвон ===')
    for корень in (r'C:\seostat\templates', r'C:\seostat\app\templates'):
        if not os.path.isdir(корень):
            continue
        for п in sorted(glob.glob(os.path.join(корень, '**', '*.html'),
                                  recursive=True)):
            имя = os.path.basename(п)
            if 'centro' in имя.lower() or 'obzvon' in имя.lower() or \
                    'call' in имя.lower():
                print(f'  {os.path.getsize(п):>9}  {п}')


if __name__ == '__main__':
    main()
