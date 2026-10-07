# -*- coding: utf-8 -*-
"""Доводка статистики: честный подсчёт «не назначено», перезапуск копии, проверка по HTTP.

ЧТО ПОЧИНЕНО И ПОЧЕМУ.
Замер дал: назначений 1638, компаний в каталоге 1620. Я считала «не назначено» как
max(0, 1620 - 1638) и получала 0 — красивый ноль, который скрывает ровно то, что админу
и надо видеть: назначения не сходятся с каталогом. Считаю множествами и показываю три
новых числа: сколько назначений смотрят на ИНН вне каталога и сколько компаний висит
больше чем на одном продавце.
"""
import io
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request

KOREN = r'C:\centro2'
ROUTES = os.path.join(KOREN, 'app', 'api', 'routes_centro_sales.py')
SHABLON = os.path.join(KOREN, 'app', 'templates', 'centro_stats.html')
VENV = r'C:\seostat\.venv\Scripts\python.exe'
PORT = 8016
LOG = os.path.join(KOREN, 'centro2.log')

itog = []


def skazat(s):
    itog.append(s)
    print(s)


# ---------------------------------------------------------------- 1. правка маршрута
t = io.open(ROUTES, encoding='utf-8').read()
STARO = '''    with sales.connect() as conn:
        obshchee = _stats_obshchee(conn)
        prodavcy = _stats_po_prodavcam(conn)
        ochered = _stats_ochered(conn, vybrannyy, imena) if vybrannyy else []
    obshchee["v_kataloge"] = vsego_v_kataloge
    obshchee["ne_naznacheno"] = max(0, vsego_v_kataloge - obshchee["naznacheno"])'''
NOVO = '''    with sales.connect() as conn:
        obshchee = _stats_obshchee(conn)
        prodavcy = _stats_po_prodavcam(conn)
        naznachennye = {str(r[0]).strip() for r in conn.execute(
            "SELECT DISTINCT inn FROM company_assignment")}
        ochered = _stats_ochered(conn, vybrannyy, imena) if vybrannyy else []
    v_kataloge = set(imena)
    # Считаю множествами, а не вычитанием двух счётчиков. Вычитание давало «не назначено
    # 0» при 1638 назначениях на 1620 компаний, то есть прятало расхождение вместо того
    # чтобы его назвать.
    obshchee["v_kataloge"] = len(v_kataloge)
    obshchee["ne_naznacheno"] = len(v_kataloge - naznachennye)
    obshchee["kompaniy_naznacheno"] = len(naznachennye & v_kataloge)
    obshchee["vne_kataloga"] = len(naznachennye - v_kataloge)
    obshchee["dvum_prodavcam"] = max(0, obshchee["naznacheno"] - len(naznachennye))'''
pravok = 0
if NOVO.split('\n')[0] and 'kompaniy_naznacheno' in t:
    skazat('маршрут уже правлен')
elif STARO in t:
    t = t.replace(STARO, NOVO, 1)
    pravok += 1
    io.open(ROUTES, 'w', encoding='utf-8').write(t)
    skazat('маршрут: правка внесена (1 из 1)')
else:
    skazat('ВНИМАНИЕ: якорь в маршруте не найден, правка НЕ внесена')

# ---------------------------------------------------------------- 2. правка шаблона
h = io.open(SHABLON, encoding='utf-8').read()
S_STARO = ('''    <div class="plitka"><b>{{ obshchee.naznacheno }}</b>'''
           '''<span>назначено продавцам</span></div>
    <div class="plitka"><b>{{ obshchee.ne_naznacheno }}</b><span>не назначено</span></div>''')
S_NOVO = ('''    <div class="plitka"><b>{{ obshchee.naznacheno }}</b>'''
          '''<span>назначений всего</span></div>
    <div class="plitka"><b>{{ obshchee.kompaniy_naznacheno }}</b>'''
          '''<span>компаний назначено</span></div>
    <div class="plitka"><b>{{ obshchee.ne_naznacheno }}</b>'''
          '''<span>компаний без продавца</span></div>
    <div class="plitka"><b class="{% if obshchee.dvum_prodavcam %}prosr{% endif %}">'''
          '''{{ obshchee.dvum_prodavcam }}</b><span>висит на двух продавцах</span></div>
    <div class="plitka"><b class="{% if obshchee.vne_kataloga %}prosr{% endif %}">'''
          '''{{ obshchee.vne_kataloga }}</b><span>назначений на ИНН вне каталога</span></div>''')
if 'компаний без продавца' in h:
    skazat('шаблон уже правлен')
elif S_STARO in h:
    h = h.replace(S_STARO, S_NOVO, 1)
    pravok += 1
    io.open(SHABLON, 'w', encoding='utf-8').write(h)
    skazat('шаблон: правка внесена (1 из 1)')
else:
    skazat('ВНИМАНИЕ: якорь в шаблоне не найден, правка НЕ внесена')

# ---------------------------------------------------------------- 3. перезапуск копии
def pid_na_portu(port):
    r = subprocess.run(['netstat', '-ano'], capture_output=True, timeout=90)
    pidy = set()
    for l in r.stdout.decode('cp866', 'replace').splitlines():
        if (':%d ' % port) in l and 'LISTENING' in l.upper():
            pidy.add(l.split()[-1])
    return pidy


bylo = pid_na_portu(PORT)
skazat('на порту %d слушали PID: %s' % (PORT, ', '.join(sorted(bylo)) or 'никто'))
for p in bylo:
    subprocess.run(['taskkill', '/PID', p, '/F'], capture_output=True, timeout=60)
time.sleep(2)

DETACHED = 0x00000008 | 0x00000200
log = io.open(LOG, 'a', encoding='utf-8', errors='replace')
log.write('\n===== перезапуск %s =====\n' % time.strftime('%Y-%m-%d %H:%M:%S'))
log.flush()
subprocess.Popen(
    [VENV, '-m', 'uvicorn', 'app.obzvon:app', '--host', '127.0.0.1',
     '--port', str(PORT)],
    cwd=KOREN, stdout=log, stderr=subprocess.STDOUT,
    creationflags=DETACHED, close_fds=True,
    env=dict(os.environ, PYTHONIOENCODING='utf-8', ENV_FILE=os.path.join(KOREN, '.env')))
for _ in range(30):
    time.sleep(1)
    if pid_na_portu(PORT):
        break
skazat('после перезапуска слушают PID: %s'
       % (', '.join(sorted(pid_na_portu(PORT))) or 'НИКТО — смотри лог'))

# ---------------------------------------------------------------- 4. проверка по HTTP
class BezRedirekta(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


opener = urllib.request.build_opener(BezRedirekta)


def proba(put):
    url = 'http://127.0.0.1:%d%s' % (PORT, put)
    try:
        o = opener.open(url, timeout=30)
        return o.status, len(o.read()), o.headers.get('Location') or ''
    except urllib.error.HTTPError as e:
        return e.code, len(e.read() or b''), e.headers.get('Location') or ''
    except Exception as e:  # noqa: BLE001
        return 'ОШИБКА', str(e)[:70], ''


for put in ('/obzvon/centro/login', '/obzvon/centro/stats',
            '/obzvon/centro/stats?user=user2', '/obzvon/centro/admin'):
    kod, dlina, kuda = proba(put)
    skazat('  %-34s -> %s, тело %s%s' % (put, kod, dlina,
                                         (', Location=' + kuda) if kuda else ''))

print('\n===== ИТОГ =====')
print('правок внесено: %d' % pravok)
for s in itog:
    print(s)
print('\nхвост лога:')
try:
    print(''.join(io.open(LOG, encoding='utf-8', errors='replace').readlines()[-12:]))
except Exception as e:  # noqa: BLE001
    print('  лог не прочитан: %s' % e)
