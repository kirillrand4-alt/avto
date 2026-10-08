# -*- coding: utf-8 -*-
"""Карточка: название не жирным, описание жирным; все длинные тире «—» -> короткие «–».

Владелец: «название не жирным сделай, а описание наоборот жирным, и все длинные тире
замени на короткие». Тире меняются везде, где их видит продавец:
  * данные базы Meyer — все текстовые поля каталога (описания с сайтов, должности,
    источники, сегменты, расшифровка балла);
  * все шаблоны панели (подписи, заглушки «—» в пустых полях, «— выберите —»);
  * подписи результатов звонка в коде («Дубль — уже работают»).
Комментарии и продажи (что пишут продавцы) не трогаются.
"""
import io
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import time

VENV = r'C:\seostat\.venv\Scripts\python.exe'
KOREN = r'C:\centro2'
APP = os.path.join(KOREN, 'app')
T = os.path.join(APP, 'templates')
KAT = os.path.join(KOREN, 'data', 'meyer_baza1.db')
CS = os.path.join(APP, 'services', 'centro_sales.py')
PORT = 8016
PUT = '/obzvon-meyer'
DL, KR = '\u2014', '\u2013'          # — длинное, – короткое
BEKAP = os.path.join(KOREN, '_bekap', time.strftime('tire-%Y%m%d-%H%M%S'))

if '--proverka' in sys.argv:
    sys.path.insert(0, KOREN)
    import zapusk  # noqa: F401
    import logging
    import warnings
    warnings.filterwarnings('ignore')
    logging.disable(logging.CRITICAL)
    from app.api import routes_centro_sales as rcs
    from app.services import centro_sales as sales
    from app.obzvon import create_app
    from fastapi.testclient import TestClient

    plohih = 0

    def proverit(u, t):
        global plohih
        if not u:
            plohih += 1
        print('   %s %s' % ('ОК ' if u else 'ПЛОХО', t))

    vnutr = next(z for z in vars(create_app()).values()
                 if hasattr(z, 'routes') and hasattr(z, 'dependency_overrides'))
    vnutr.dependency_overrides[rcs.current_user] = lambda: {
        'id': 0, 'username': 'meyer_admin', 'role': 'admin', 'is_active': 1}
    podpisi = [str(v) for v in vars(sales).values() if isinstance(v, (dict, list, tuple))
               for v in (v.values() if isinstance(v, dict) else v) if 'Дубль' in str(v)]
    proverit(podpisi and all(DL not in v for v in podpisi), 'подписи результатов в коде: %s' % podpisi)
    with TestClient(vnutr) as k:
        kat = sqlite3.connect(KAT)
        inn = kat.execute("select inn from company where opisanie like '%' || ? || '%' limit 1", (KR,)).fetchone()
        inn = inn[0] if inn else kat.execute('select inn from company limit 1').fetchone()[0]
        for s in ('/centro', '/centro?inn=' + inn, '/centro/stats', '/centro/admin', '/centro/spisok'):
            o = k.get(PUT + s)
            # всё, что видно, включая подсказки title/placeholder: без <script>/<style>/комментариев
            vid = re.sub(r'<script.*?</script>|<style.*?</style>|<!--.*?-->', '', o.text, flags=re.S)
            proverit(o.status_code == 200 and DL not in vid,
                     '%-26s -> %s, длинных тире %d, коротких %d' % (s[:26], o.status_code, vid.count(DL), vid.count(KR)))
        t = k.get(PUT + '/centro?inn=' + inn).text
        proverit('.company-hero h1{font-weight:400}' in t and '.company-hero .opisanie{font-weight:700' in t,
                 'в карточке название обычным, описание жирным')
        m = re.search(r'<p class="opisanie"[^>]*>([^<]*)</p>', t)
        print('      описание: %r' % (m.group(1)[:80] if m else None))
    print()
    print('ПЛОХИХ ПРОВЕРОК: %d' % plohih)
    raise SystemExit(0)

os.makedirs(BEKAP, exist_ok=True)

# ---------- 1. данные каталога
shutil.copy2(KAT, os.path.join(BEKAP, 'meyer_baza1.db'))
k = sqlite3.connect(KAT)
vsego = 0
for (tabl,) in k.execute("select name from sqlite_master where type='table' and name not like 'sqlite_%'").fetchall():
    for r in k.execute('PRAGMA table_info("%s")' % tabl).fetchall():
        kol, tip = r[1], (r[2] or '').upper()
        if 'INT' in tip or 'REAL' in tip:
            continue
        n = k.execute('select count(*) from "%s" where instr("%s", ?)>0' % (tabl, kol), (DL,)).fetchone()[0]
        if n:
            k.execute('update "%s" set "%s"=replace("%s", ?, ?) where instr("%s", ?)>0'
                      % (tabl, kol, kol, kol), (DL, KR, DL))
            vsego += n
            print('   данные: %s.%s — %d строк' % (tabl, kol, n))
k.commit()
k.close()
print('данные каталога: заменено в %d значениях' % vsego)

# ---------- 2. шаблоны
vsego = 0
for f in sorted(os.listdir(T)):
    if not f.endswith('.html'):
        continue
    p = os.path.join(T, f)
    t = io.open(p, encoding='utf-8').read()
    n = t.count(DL)
    if n:
        shutil.copy2(p, os.path.join(BEKAP, f))
        io.open(p, 'w', encoding='utf-8').write(t.replace(DL, KR))
        vsego += n
        print('   шаблон %-24s %d' % (f, n))
print('шаблоны: заменено %d' % vsego)

# ---------- 3. строки в коде, которые видит продавец (разведка probe_tire: заглушки «—»
# для пустых значений, подпись «Дубль — уже работают», строки парка). Регулярки вида
# [-–—] НЕ трогаются: они разбирают ввод, где длинное тире может встретиться.
KOD = {
    os.path.join(APP, 'web.py'): ['"—"'],
    os.path.join(APP, 'services', 'centro_catalog.py'): ['"—"'],
    os.path.join(APP, 'services', 'callbase.py'): ['"—"'],
    CS: ['"Дубль — уже работают"'],
    os.path.join(APP, 'api', 'routes_park.py'): ['"%s — %s: %s%s"', '"%s — %s"'],
}
vsego = 0
for p, stroki in KOD.items():
    t = io.open(p, encoding='utf-8').read()
    n = 0
    for s in stroki:
        n += t.count(s)
        t = t.replace(s, s.replace(DL, KR))
    if n:
        shutil.copy2(p, os.path.join(BEKAP, os.path.basename(p)))
        io.open(p, 'w', encoding='utf-8').write(t)
    vsego += n
    print('   код %-22s %d' % (os.path.basename(p), n))
print('строки в коде: заменено %d' % vsego)

# ---------- 4. карточка: название обычным, описание жирным
C = os.path.join(T, 'centro.html')
t = io.open(C, encoding='utf-8').read()
if '.company-hero h1{font-weight:400}' in t:
    print('жирность: уже правлено')
elif t.count('.hide-company{margin:8px 0 0;') == 1:
    t = t.replace('.hide-company{margin:8px 0 0;',
                  '.company-hero h1{font-weight:400}\n'
                  '.company-hero .opisanie{font-weight:700;color:var(--navy)}\n'
                  '.hide-company{margin:8px 0 0;', 1)
    io.open(C, 'w', encoding='utf-8').write(t)
    print('жирность: название обычным, описание жирным')
else:
    print('жирность: ЯКОРЬ НЕ НАЙДЕН')
print('бэкап: %s' % BEKAP)

sreda = dict(os.environ, PYTHONIOENCODING='utf-8')
p = subprocess.run(['netstat', '-ano'], capture_output=True, timeout=90)
for l in p.stdout.decode('cp866', 'replace').splitlines():
    if (':%d ' % PORT) in l and 'LISTENING' in l.upper():
        subprocess.run(['taskkill', '/PID', l.split()[-1], '/F'], capture_output=True, timeout=60)
time.sleep(2)
lg = io.open(os.path.join(KOREN, 'centro2.log'), 'a', encoding='utf-8', errors='replace')
lg.write('\n===== перезапуск: тире и жирность %s =====\n' % time.strftime('%Y-%m-%d %H:%M:%S'))
lg.flush()
subprocess.Popen([VENV, os.path.join(KOREN, 'zapusk.py')], cwd=KOREN, stdout=lg,
                 stderr=subprocess.STDOUT, creationflags=0x00000008 | 0x00000200,
                 close_fds=True, env=sreda)
time.sleep(10)
r = subprocess.run([VENV, os.path.abspath(__file__), '--proverka'], capture_output=True,
                   timeout=900, cwd=KOREN, env=sreda)
print()
print('===== ПРОВЕРКА =====')
sys.stdout.write(r.stdout.decode('utf-8', 'replace'))
if r.returncode:
    sys.stdout.write('\n--- stderr ---\n' + r.stderr.decode('utf-8', 'replace')[-3000:])
