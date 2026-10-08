# -*- coding: utf-8 -*-
"""Исправитель A2: только чтение – замок, перезапуски в журнале панели, порт, бэкапы, признаки в живых файлах."""
import io
import os
import subprocess
import urllib.request

KOREN = r'C:\centro2'
zam = os.path.join(KOREN, '_zamok.txt')
print('замок:', io.open(zam, encoding='utf-8').read() if os.path.exists(zam) else 'свободен')
lg = io.open(os.path.join(KOREN, 'centro2.log'), encoding='utf-8', errors='replace').read()
print('перезапуски (последние):')
for l in [x for x in lg.splitlines() if 'перезапуск' in x][-6:]:
    print('  ', l)
p = subprocess.run(['netstat', '-ano'], capture_output=True, timeout=90)
for l in p.stdout.decode('cp866', 'replace').splitlines():
    if ':8016 ' in l and 'LISTENING' in l.upper():
        print('порт:', ' '.join(l.split()))
try:
    print('вход:', urllib.request.urlopen('http://127.0.0.1:8016/obzvon-meyer/centro/login', timeout=30).status)
except Exception as e:  # noqa: BLE001
    print('вход: ошибка', str(e)[:100])
b = os.path.join(KOREN, '_bekap')
print('бэкапы A2:', sorted(x for x in os.listdir(b) if x.startswith('fixA2'))[-5:])
c = io.open(os.path.join(KOREN, 'app', 'templates', 'centro.html'), encoding='utf-8').read()
w = io.open(os.path.join(KOREN, 'app', 'web.py'), encoding='utf-8').read()
print('centro.html: fixA2-vid %s, kontakt_vid %s; web.py: метка %s, chuzhoy в _vid_istochnika %s' % (
    'id="fixA2-vid"' in c, "kontakt_vid(contact" in c, 'исправитель A2' in w,
    'def _vid_istochnika(url, source="", sayt="", chuzhoy="")' in w))
