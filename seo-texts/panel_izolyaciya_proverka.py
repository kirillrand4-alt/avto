# -*- coding: utf-8 -*-
"""Дочистка проверки загрузчика: служебные атрибуты (__doc__ и т.п.) не считаются.

Первый прогон засчитал docstring routes_park как «строку с боевым путём» — там в тексте
описания упомянут C:\\seostat\\data\\park_panel.db. Это не путь, по которому что-то
открывается, и он забил собой вывод. Смотрим только настоящие переменные модулей.
"""
import io
import os
import subprocess

VENV = r'C:\seostat\.venv\Scripts\python.exe'
KOREN = r'C:\centro2'
Z = os.path.join(KOREN, 'zapusk.py')

t = io.open(Z, encoding='utf-8').read()
staro = '            for atr, v in list(vars(mod).items()):\n                if isinstance(v, str)'
novo = ('            for atr, v in list(vars(mod).items()):\n'
        '                if atr.startswith("__"):\n'
        '                    continue    # docstring и прочее служебное — не пути\n'
        '                if isinstance(v, str)')
if 'atr.startswith("__")' in t:
    print('zapusk.py: уже правлен')
elif staro in t:
    io.open(Z, 'w', encoding='utf-8').write(t.replace(staro, novo, 1))
    print('zapusk.py: служебные атрибуты исключены из проверки')
else:
    print('zapusk.py: ЯКОРЬ НЕ НАЙДЕН')

r = subprocess.run([VENV, Z, '--proverka'], capture_output=True, timeout=600, cwd=KOREN,
                   env=dict(os.environ, PYTHONIOENCODING='utf-8'))
print('rc=%s' % r.returncode)
print((r.stdout + r.stderr).decode('utf-8', 'replace').strip()[-3000:])
