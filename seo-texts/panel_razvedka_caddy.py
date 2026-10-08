# -*- coding: utf-8 -*-
"""Живой конфиг Caddy и как считается obzvon_path.

Файлы nginx*.conf в C:\\seostat\\deploy — устаревшая документация: на 80/443 висит
caddy.exe. Поэтому спрашиваю не диск, а сам Caddy через его admin API: это единственный
источник, который совпадает с тем, что реально работает.
"""
import io
import json
import os
import re
import subprocess
import urllib.error
import urllib.request

OTCHET = r'C:\seostat\drop\drop-storage\razvedka-caddy.txt'
vyhod = []
svodka = []


def pishi(s=''):
    vyhod.append(str(s))


def svodno(s):
    svodka.append(str(s))
    vyhod.append(str(s))


# ---------------------------------------------------------------- 1. obzvon_path
pishi('########## app/config.py вокруг obzvon_path')
p = r'C:\centro2\app\config.py'
stroki = io.open(p, encoding='utf-8', errors='replace').read().splitlines()
for i, l in enumerate(stroki, 1):
    if 40 <= i <= 110:
        pishi('   %4d: %s' % (i, l.rstrip()[:170]))
tekst = '\n'.join(stroki)
m = re.search(r'def obzvon_path.*?(?=\n    @|\n    def |\nclass |\Z)', tekst, re.S)
if m:
    svodno('obzvon_path считается так: %s'
           % ' / '.join(l.strip() for l in m.group(0).splitlines() if l.strip())[:300])
# какие поля окружения вообще есть у настроек
polya = re.findall(r'^\s{4}([a-z][a-z0-9_]*)\s*:\s*[^=\n]+=', tekst, re.M)
svodno('полей настроек: %d, среди них со словом path/obzvon: %s'
       % (len(polya), [x for x in polya if 'path' in x or 'obzvon' in x] or 'нет'))

# ---------------------------------------------------------------- 2. командная строка Caddy
pishi()
pishi('########## ЧЕМ ЗАПУЩЕН CADDY')
try:
    r = subprocess.run(
        ['wmic', 'process', 'where', "name='caddy.exe'", 'get',
         'ProcessId,ExecutablePath,CommandLine', '/format:list'],
        capture_output=True, timeout=120)
    t = r.stdout.decode('cp866', 'replace')
    if not t.strip():
        r = subprocess.run(
            ['powershell', '-NoProfile', '-Command',
             "Get-CimInstance Win32_Process -Filter \"name='caddy.exe'\""
             " | Select-Object ProcessId,ExecutablePath,CommandLine | Format-List"],
            capture_output=True, timeout=180)
        t = r.stdout.decode('cp866', 'replace')
    for l in t.splitlines():
        if l.strip():
            pishi('   %s' % l.strip()[:300])
            if 'config' in l.lower() or 'caddyfile' in l.lower() or 'ExecutablePath' in l:
                svodno(l.strip()[:200])
except Exception as e:  # noqa: BLE001
    pishi('   не получилось: %s' % e)

# ---------------------------------------------------------------- 3. admin API
pishi()
pishi('########## ЖИВОЙ КОНФИГ ЧЕРЕЗ ADMIN API 2019')
konf = None
try:
    o = urllib.request.urlopen('http://127.0.0.1:2019/config/', timeout=20)
    syroy = o.read().decode('utf-8', 'replace')
    konf = json.loads(syroy)
    io.open(r'C:\seostat\drop\drop-storage\caddy-config.json', 'w',
            encoding='utf-8').write(json.dumps(konf, ensure_ascii=False, indent=1))
    svodno('admin API ответил, конфиг положен на дроп: caddy-config.json (%d знаков)'
           % len(syroy))
except Exception as e:  # noqa: BLE001
    svodno('admin API недоступен: %s' % str(e)[:90])

if konf:
    srv = ((konf.get('apps') or {}).get('http') or {}).get('servers') or {}
    svodno('серверов http: %s' % ', '.join(srv) or 'нет')
    for imya, s in srv.items():
        pishi('--- сервер %s, слушает %s' % (imya, s.get('listen')))
        marshruty = s.get('routes') or []
        pishi('    маршрутов: %d' % len(marshruty))
        for mr in marshruty:
            soglas = mr.get('match') or []
            puti = []
            hosty = []
            for so in soglas:
                puti += so.get('path') or []
                hosty += so.get('host') or []
            kuda = []

            def sobrat(uzly):
                for h in uzly or []:
                    if h.get('handler') == 'reverse_proxy':
                        for up in h.get('upstreams') or []:
                            kuda.append(up.get('dial', '?'))
                    if h.get('handler') == 'subroute':
                        for vm in h.get('routes') or []:
                            sobrat(vm.get('handle'))
                    if h.get('handler') == 'static_response':
                        kuda.append('ответ %s -> %s' % (h.get('status_code'),
                                                        (h.get('headers') or {})))
                    if h.get('handler') == 'file_server':
                        kuda.append('файлы %s' % h.get('root', ''))
                    if h.get('handler') == 'rewrite':
                        kuda.append('rewrite %s' % h.get('uri', h.get('strip_path_prefix', '')))
            sobrat(mr.get('handle'))
            stroka = ('    хосты %-44s пути %-34s -> %s'
                      % (','.join(hosty)[:44] or '*', ','.join(puti)[:34] or '*',
                         ', '.join(kuda)[:90] or '?'))
            pishi(stroka)
            if '8012' in ' '.join(kuda) or 'obzvon' in ' '.join(puti):
                svodno(stroka.strip())

# ---------------------------------------------------------------- 4. Caddyfile на диске
pishi()
pishi('########## CADDYFILE НА ДИСКЕ')
nashlos = []
for baza in (r'C:\caddy', r'C:\Caddy', r'C:\seostat', r'C:\ProgramData\Caddy',
             r'C:\Users\Administrator', r'C:\\'):
    if not os.path.isdir(baza):
        continue
    glubina = baza.count(os.sep)
    for kor, kat, fajly in os.walk(baza):
        if kor.count(os.sep) - glubina > (1 if baza == 'C:\\\\' else 3):
            kat[:] = []
            continue
        kat[:] = [d for d in kat if d.lower() not in (
            '.git', 'node_modules', '__pycache__', '.venv', 'drop-storage', 'dokaz',
            'windows', 'program files', 'program files (x86)', 'appdata', '$recycle.bin')]
        for f in fajly:
            if f.lower().startswith('caddyfile') or f.lower() == 'caddy.json':
                nashlos.append(os.path.join(kor, f))
for q in sorted(set(nashlos))[:10]:
    try:
        t = io.open(q, encoding='utf-8', errors='replace').read()
    except OSError:
        continue
    pishi('--- %s (%d знаков)' % (q, len(t)))
    for i, l in enumerate(t.splitlines(), 1):
        if l.strip():
            pishi('   %4d: %s' % (i, l.rstrip()[:170]))
    if 'obzvon' in t or '8012' in t:
        svodno('Caddyfile с обзвоном: %s' % q)
svodno('Caddyfile-ов найдено: %d' % len(set(nashlos)))

io.open(OTCHET, 'w', encoding='utf-8').write('\n'.join(vyhod))
print('полный отчёт: %s (%d строк)' % (OTCHET, len(vyhod)))
print('\n===== СВОДКА =====')
for s in svodka:
    print(s)
