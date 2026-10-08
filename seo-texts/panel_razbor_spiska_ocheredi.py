# -*- coding: utf-8 -*-
"""Как устроена страница «Вся очередь»: одна карточка или есть готовый режим списка.

Владелец: «вся очередь списком с основными данными в списке, когда проваливаешься в
компанию — тогда открывается карточка». В шаблонах есть centro_list.html («Строки 1–20
из N», выбор размера страницы) и кнопка «Вид». Прежде чем строить список, надо понять,
не существует ли он уже и чем включается.
"""
import io
import os
import re

KOREN = r'C:\centro2'
APP = os.path.join(KOREN, 'app')
OTCHET = r'C:\seostat\drop\drop-storage\razbor-spiska-ocheredi.txt'
vyhod = []


def pishi(s=''):
    vyhod.append(str(s))


# 1. кто использует centro_list.html / centro_card.html
pishi('########## ГДЕ УПОМИНАЮТСЯ centro_list / centro_card')
for kor, kat, fajly in os.walk(APP):
    kat[:] = [d for d in kat if '__pycache__' not in d and 'dokaz' not in d]
    for f in sorted(fajly):
        if not f.endswith(('.py', '.html', '.js')):
            continue
        p = os.path.join(kor, f)
        for i, l in enumerate(io.open(p, encoding='utf-8', errors='replace'), 1):
            if re.search(r'centro_list|centro_card', l):
                pishi('   %s:%d  %s' % (os.path.relpath(p, KOREN), i, l.strip()[:160]))

# 2. маршрут /centro: параметры и что уходит в шаблон
RCS = os.path.join(APP, 'api', 'routes_centro_sales.py')
t = io.open(RCS, encoding='utf-8', errors='replace').read().splitlines()
nach = next((i for i, l in enumerate(t) if re.search(r'@router\.get\("/centro"\)', l)), None)
pishi()
pishi('########## МАРШРУТ /centro (routes_centro_sales.py)')
if nach is not None:
    for j in range(nach, min(len(t), nach + 250)):
        pishi('   %4d: %s' % (j + 1, t[j].rstrip()[:170]))
        if j > nach + 5 and t[j].startswith('@router.'):
            break

# 3. центральная разметка centro.html: крупные блоки, «Вид», очередь
C = os.path.join(APP, 'templates', 'centro.html')
ct = io.open(C, encoding='utf-8', errors='replace').read().splitlines()
pishi()
pishi('########## centro.html: строки с очередью, видом, списком, блоками (%d строк)' % len(ct))
for i, l in enumerate(ct, 1):
    if re.search(r'<(main|aside|section|nav)\b|queue|ochered|Вид|vid=|view|layout|'
                 r'data-frag|companies|chosen|for c in|for company|из {{|res\.|page_sizes|'
                 r'class="(list|spisok|table)', l):
        pishi('   %4d: %s' % (i, l.rstrip()[:175]))

# 4. JS: что делает кнопка «Вид»
pishi()
pishi('########## JS в centro.html вокруг «Вид»')
tekst = '\n'.join(ct)
for m in re.finditer(r'Вид', tekst):
    a = tekst.rfind('\n', 0, max(0, m.start() - 900))
    b = tekst.find('\n', m.end() + 900)
    pishi(tekst[a:b])
    pishi('-' * 60)
    break

io.open(OTCHET, 'w', encoding='utf-8').write('\n'.join(vyhod))
print('разбор: %s (%d строк)' % (OTCHET, len(vyhod)))
