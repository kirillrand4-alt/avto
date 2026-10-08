# -*- coding: utf-8 -*-
"""Разметка всех вхождений «/centro» в копии перед переименованием сегмента пути.

ЗАЧЕМ РАЗМЕТКА, А НЕ СРАЗУ ЗАМЕНА. Среди вхождений есть `static/centro/dokaz` — каталог
скриншотов-доказательств. Слепая замена «/centro» на «/obzvon» превратила бы его в
`static/obzvon/dokaz`, и 12 108 картинок перестали бы открываться, причём страница при
этом осталась бы на вид рабочей. Поэтому сперва каждое вхождение относится к одному из
классов, и только потом правится то, что относится к маршруту.

КЛАССЫ
  marshrut   путь маршрута или ссылка на страницу — это и надо переименовать
  statika    /static/centro... — НЕ трогать
  css        centro.css — НЕ трогать
  kommentar  в комментарии или в тексте для человека — не влияет на работу
  prochee    всё, что не распознано: смотреть глазами
"""
import io
import os
import re

KOREN = r'C:\centro2'
OTCHET = r'C:\seostat\drop\drop-storage\razmetka-centro.txt'

vyhod = []
schet = {}
primery = {}


def klass(fajl, stroka, poz):
    okno = stroka[max(0, poz - 30):poz + 24]
    if '/static/centro' in okno or 'static\\centro' in okno:
        return 'statika'
    if re.search(r'/centro[-_a-zA-Z0-9]*\.(css|js|png|jpg|svg|ico)', okno):
        return 'css'
    golaya = stroka.strip()
    if fajl.endswith('.py') and (golaya.startswith('#') or golaya.startswith('*')
                                 or golaya.startswith('"""') or golaya.startswith("'")):
        return 'kommentar'
    if fajl.endswith('.html') and ('{#' in stroka or '<!--' in stroka):
        return 'kommentar'
    if re.search(r'["\']/centro', stroka) or '}}/centro' in stroka \
            or re.search(r'\{\{\s*base_path\s*\}\}/centro', stroka) \
            or re.search(r'(BP|OBZ|obz)\s*\+\s*["\']/centro', stroka) \
            or re.search(r'f["\'][^"\']*\{(BP|OBZ|obz)\}/centro', stroka):
        return 'marshrut'
    return 'prochee'


for kor, kat, fajly in os.walk(os.path.join(KOREN, 'app')):
    kat[:] = [d for d in kat if '__pycache__' not in d and 'dokaz' not in d]
    for f in sorted(fajly):
        if not f.endswith(('.py', '.html', '.js', '.css')):
            continue
        p = os.path.join(kor, f)
        otn = os.path.relpath(p, KOREN)
        for n, l in enumerate(io.open(p, encoding='utf-8', errors='replace'), 1):
            for m in re.finditer(r'/centro', l):
                k = klass(f, l, m.start())
                schet[k] = schet.get(k, 0) + 1
                primery.setdefault(k, []).append(
                    '%s:%d  %s' % (otn, n, l.strip()[:150]))
                vyhod.append('[%-9s] %s:%d  %s' % (k, otn, n, l.strip()[:160]))

io.open(OTCHET, 'w', encoding='utf-8').write('\n'.join(vyhod))

print('полная разметка: %s (%d строк)' % (OTCHET, len(vyhod)))
print('\n===== СКОЛЬКО ЧЕГО =====')
for k in sorted(schet, key=lambda x: -schet[x]):
    print('   %-10s %4d' % (k, schet[k]))
print('\n===== ЧТО НЕ РАСПОЗНАНО (смотреть глазами) =====')
for s in primery.get('prochee', [])[:25]:
    print('   %s' % s)
print('\n===== СТАТИКА И CSS: ЭТО НЕ ТРОГАЕМ =====')
for k in ('statika', 'css'):
    for s in primery.get(k, [])[:8]:
        print('   [%s] %s' % (k, s))
