# -*- coding: utf-8 -*-
r"""fixKO (21.10): разведка перед переводом главной КЦ (/obzvon/centro) в список, как у Meyer. Только чтение.

Код обеих панелей (C:\seostat\app и C:\centro2\app: *.py, шаблоны, css/js) – архивом на дроп
`fixKO-kod.tar.gz`; замки, службы, кто слушает 8012/8014/8016.

    python3 zapusk_na_servere.py fixKO_razvedka.py
"""
import io
import os
import subprocess
import tarfile

DROP = r'C:\seostat\drop\drop-storage'


def sh(cmd, kod='cp866'):
    r = subprocess.run(cmd, shell=True, capture_output=True, timeout=120)
    return r.stdout.decode(kod, 'replace')


for z in (r'C:\seostat\_zamok.txt', r'C:\centro2\_zamok.txt'):
    print('замок %s: %s' % (z, io.open(z, encoding='utf-8', errors='replace').read()[:200] if os.path.exists(z) else 'нет'))
for l in sh('netstat -ano').splitlines():
    if 'LISTENING' in l.upper() and any((':%d ' % p) in l for p in (8011, 8012, 8014, 8016)):
        print('  ', ' '.join(l.split()))
for svc in ('obzvon', 'p25obzvon', 'seostat'):
    print('служба %s: %s' % (svc, ' '.join(sh('sc query %s' % svc).split())[:160]))

ark = os.path.join(DROP, 'fixKO-kod.tar.gz')
n = 0
with tarfile.open(ark, 'w:gz') as tf:
    for koren, metka in ((r'C:\seostat', 'seostat'), (r'C:\centro2', 'centro2')):
        app = os.path.join(koren, 'app')
        for dp, dn, fn in os.walk(app):
            dn[:] = [d for d in dn if d not in ('__pycache__', 'dokaz', 'node_modules') and not os.path.islink(os.path.join(dp, d))]
            for f in fn:
                if not f.endswith(('.py', '.html', '.css', '.js', '.txt', '.json')):
                    continue
                p = os.path.join(dp, f)
                if os.path.getsize(p) > 3 * 2**20:
                    continue
                tf.add(p, arcname=metka + '/' + os.path.relpath(p, koren).replace('\\', '/'))
                n += 1
        for f in ('zapusk.py',):
            p = os.path.join(koren, f)
            if os.path.exists(p):
                tf.add(p, arcname=metka + '/' + f)
print('архив: %s, файлов %d, %.1f МБ' % (ark, n, os.path.getsize(ark) / 2**20))
