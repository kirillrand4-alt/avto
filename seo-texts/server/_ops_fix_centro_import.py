# -*- coding: utf-8 -*-
"""Починка импорта роутера centro в C:\\seostat\\app\\obzvon.py.

Моя ошибка: вставил `from api import routes_centro`, тогда как приложение
поднимается как `app.obzvon:app` из C:\\seostat, и корень пакета — `app`.
Боевой код импортирует `from app.api import routes_obzvon` (obzvon.py:24),
значит и наш импорт обязан быть `from app.api import routes_centro`.

Проверяем импортом ДО перезапуска службы, чтобы не оставить панель лежать.
"""
import json
import os
import subprocess
import sys
import time

APP = r'C:\seostat\app'
F = os.path.join(APP, 'obzvon.py')
VENV_PY = r'C:\seostat\.venv\Scripts\python.exe'


def main():
    apply = len(sys.argv) > 1 and sys.argv[1] == 'apply'
    out = {'режим': 'ПРИМЕНЕНИЕ' if apply else 'сухой прогон'}
    txt = open(F, encoding='utf-8', errors='replace').read()
    bad = 'from api import routes_centro'
    good = 'from app.api import routes_centro'
    out['есть_плохой_импорт'] = bad in txt
    out['уже_исправлен'] = good in txt

    if bad in txt and apply:
        open(F + f'.bak-fix-{int(time.time())}', 'w', encoding='utf-8').write(txt)
        open(F, 'w', encoding='utf-8').write(txt.replace(bad, good))
        out['исправлено'] = True
        txt = open(F, encoding='utf-8', errors='replace').read()

    i = txt.find('routes_centro')
    out['вставка'] = txt[max(0, i - 200):i + 160] if i >= 0 else '(нет)'

    # ПРОВЕРКА импорта тем же интерпретатором и с тем же cwd, что у службы
    py = VENV_PY if os.path.exists(VENV_PY) else sys.executable
    r = subprocess.run([py, '-c', 'import app.obzvon; print("IMPORT OK")'],
                       capture_output=True, text=True, encoding='utf-8',
                       errors='replace', cwd=r'C:\seostat', timeout=180)
    out['импорт_rc'] = r.returncode
    out['импорт'] = ((r.stdout or '') + (r.stderr or ''))[-900:]
    print(json.dumps(out, ensure_ascii=False))


if __name__ == '__main__':
    main()
