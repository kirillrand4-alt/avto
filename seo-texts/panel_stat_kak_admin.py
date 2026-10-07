# -*- coding: utf-8 -*-
"""Проверка страницы как её увидит админ: реальный запрос к приложению, 200 и числа.

303 на логин доказывает только то, что маршрут есть. Правка счётчиков делалась внутри
маршрута, значит проверять надо сам маршрут, а не мой собранный вручную контекст: в Jinja
отсутствующий ключ рендерится пустотой, и битый счётчик выглядел бы как пустая плитка.
Авторизация подменяется через dependency_overrides — пароль админа не нужен и не печатается.
"""
import io
import os
import re
import subprocess
import sys
import traceback

VENV = r'C:\seostat\.venv\Scripts\python.exe'
if os.path.normcase(VENV) != os.path.normcase(sys.executable):
    r = subprocess.run([VENV, os.path.abspath(__file__)] + sys.argv[1:],
                       capture_output=True, timeout=1500,
                       env=dict(os.environ, PYTHONIOENCODING='utf-8'))
    sys.stdout.write(r.stdout.decode('utf-8', 'replace'))
    sys.stderr.write(r.stderr.decode('utf-8', 'replace'))
    raise SystemExit(r.returncode)

os.chdir(r'C:\centro2')
sys.path.insert(0, r'C:\centro2')
try:
    from dotenv import load_dotenv
    load_dotenv(r'C:\centro2\.env', override=True)
except Exception:  # noqa: BLE001
    pass

itog = []


def skazat(s):
    itog.append(s)
    print(s)


from app.api import routes_centro_sales as rcs  # noqa: E402
from app.obzvon import create_app  # noqa: E402

vnesh = create_app()
# create_app отдаёт обёртку BasicAuthASGI; внутри лежит само приложение FastAPI.
vnutr = None
for imya, znach in vars(vnesh).items():
    if hasattr(znach, 'routes') and hasattr(znach, 'dependency_overrides'):
        vnutr = znach
        skazat('приложение FastAPI внутри обёртки: атрибут .%s' % imya)
        break
if vnutr is None:
    skazat('НЕ НАШЛА приложение внутри обёртки; атрибуты: %s' % list(vars(vnesh)))
    raise SystemExit(1)

puti = sorted({getattr(r, 'path', '') for r in vnutr.routes})
skazat('маршрутов %d, со словом stats: %s'
       % (len(puti), [p for p in puti if 'stats' in p] or 'НЕТ'))

vnutr.dependency_overrides[rcs.current_user] = lambda: {
    'username': 'admin', 'role': 'admin', 'is_active': 1}

from fastapi.testclient import TestClient  # noqa: E402

with TestClient(vnutr) as klient:
    for put in ('/obzvon/centro/stats', '/obzvon/centro/stats?user=user2',
                '/obzvon/centro/stats?user=net_takogo'):
        try:
            o = klient.get(put)
            skazat('%-40s -> %s, %d знаков' % (put, o.status_code, len(o.text)))
            if o.status_code != 200:
                skazat('   тело: %s' % o.text[:400].replace('\n', ' '))
                continue
            if put.endswith('stats'):
                html = o.text
            elif 'user=user2' in put:
                io.open(r'C:\seostat\drop\drop-storage\centro2-stats-ochered.html', 'w',
                        encoding='utf-8').write(o.text)
                skazat('   страница очереди user2 положена на дроп:'
                       ' centro2-stats-ochered.html (%d знаков)' % len(o.text))
        except Exception:  # noqa: BLE001
            skazat('%s ПАДАЕТ:\n%s' % (put, traceback.format_exc()[-1200:]))

# --- какие числа реально нарисовались в плитках
try:
    plitki = re.findall(
        r'<b[^>]*>([^<]*)</b><span>([^<]+)</span>', html)
    skazat('плиток найдено %d:' % len(plitki))
    for znach, podpis in plitki:
        skazat('   %-38s %s' % (podpis, znach.strip()))
    io.open(r'C:\seostat\drop\drop-storage\centro2-stats-admin.html', 'w',
            encoding='utf-8').write(html)
    skazat('страница как её видит админ положена на дроп: centro2-stats-admin.html')
except Exception:  # noqa: BLE001
    skazat('разбор плиток не удался:\n%s' % traceback.format_exc()[-800:])

print('\n===== ИТОГ =====')
for s in itog:
    print(s)
