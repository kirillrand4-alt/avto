# -*- coding: utf-8 -*-
"""Шапки всех страниц панели: какая где, чем отмечена активная вкладка, какие переменные.

Владелец: «когда переходишь между вкладками появляется куча новых шапок». Чтобы сделать
одну шапку на всё, надо знать точно: какие шаблоны — это целые страницы (у них своя
шапка), какие — вставки; как называется переменная префикса (base_path или bp); как
главная страница отмечает активную вкладку.
"""
import io
import os
import re

KOREN = r'C:\centro2'
T = os.path.join(KOREN, 'app', 'templates')
OTCHET = r'C:\seostat\drop\drop-storage\razbor-shapok.txt'
vyhod = []


def pishi(s=''):
    vyhod.append(str(s))


for f in sorted(os.listdir(T)):
    if not (f.endswith('.html') and (f.startswith('centro') or f.startswith('park')
                                     or f.startswith('spisok'))):
        continue
    t = io.open(os.path.join(T, f), encoding='utf-8', errors='replace').read()
    pishi('=' * 100)
    pishi('%s  (%d знаков)  целая страница: %s  extends: %s  include: %s'
          % (f, len(t), '<html' in t, re.findall(r'{%\s*extends[^%]*%}', t),
             re.findall(r'{%\s*include[^%]*%}', t)))
    pishi('  префикс: base_path %d раз, bp %d раз; request в шаблоне: %d'
          % (len(re.findall(r'\bbase_path\b', t)), len(re.findall(r'\{\{\s*bp\s*\}\}', t)),
             len(re.findall(r'\brequest\b', t))))
    m = re.search(r'<header.*?</header>', t, re.S)
    if m:
        pishi('  --- шапка (%d знаков):' % len(m.group(0)))
        for l in m.group(0).splitlines():
            if l.strip():
                pishi('     %s' % l.rstrip()[:190])
    else:
        pishi('  --- тега <header> нет')
    m = re.search(r'<title>(.*?)</title>', t, re.S)
    pishi('  title: %s' % (m.group(1).strip() if m else '—'))

# какие маршруты какие шаблоны отдают
pishi()
pishi('=' * 100)
pishi('КТО КАКОЙ ШАБЛОН ОТДАЁТ')
for kor, kat, fajly in os.walk(os.path.join(KOREN, 'app', 'api')):
    kat[:] = [d for d in kat if '__pycache__' not in d]
    for f in sorted(fajly):
        if not f.endswith('.py'):
            continue
        t = io.open(os.path.join(kor, f), encoding='utf-8', errors='replace').read()
        put = None
        for i, l in enumerate(t.splitlines(), 1):
            m = re.search(r'@router\.(get|post)\(\s*"([^"]+)"', l)
            if m:
                put = m.group(2)
            m = re.search(r'"((?:centro|park|spisok)[a-z_]*\.html)"', l)
            if m:
                pishi('  %-28s %-34s %s:%d' % (m.group(1), put, f, i))

# css: класс активной вкладки и шапки
css = os.path.join(KOREN, 'app', 'static', 'css', 'centro.css')
t = io.open(css, encoding='utf-8', errors='replace').read()
pishi()
pishi('=' * 100)
pishi('centro.css: правила шапки')
for blok in re.findall(r'[^{}]*(?:topbar|brand-block|user-block|topbar-nav|\.active)[^{}]*\{[^}]*\}', t):
    pishi('  ' + re.sub(r'\s+', ' ', blok).strip()[:200])

io.open(OTCHET, 'w', encoding='utf-8').write('\n'.join(vyhod))
print('разбор: %s (%d строк)' % (OTCHET, len(vyhod)))
