# -*- coding: utf-8 -*-
"""Описание с сайта в списке — целиком, без обрезки до трёх строк (просьба владельца)."""
import io
import os
import shutil
import time

P = r'C:\centro2\app\templates\_ochered_spisok.html'
BEKAP = os.path.join(r'C:\centro2\_bekap', time.strftime('opisanie-%Y%m%d-%H%M%S'))
t = io.open(P, encoding='utf-8').read()
pravki = [
    ('.komp-opis{flex:1 1 auto;max-width:460px;color:var(--muted);font-size:12px;line-height:1.4;\n'
     '  display:-webkit-box;-webkit-line-clamp:3;-webkit-box-orient:vertical;overflow:hidden}',
     '.komp-opis{flex:1 1 auto;max-width:520px;color:var(--muted);font-size:12px;line-height:1.4}'),
    # подсказка при наведении больше не нужна: текст и так виден весь
    ('<div class="komp-opis" title="{{ c.opisanie }}">', '<div class="komp-opis">'),
]
sdelano = 0
for staro, novo in pravki:
    if novo in t:
        sdelano += 1
    elif t.count(staro) == 1:
        t = t.replace(staro, novo, 1)
        sdelano += 1
    else:
        print('ЯКОРЬ НЕ НАЙДЕН: %s' % staro[:60])
os.makedirs(BEKAP, exist_ok=True)
shutil.copy2(P, os.path.join(BEKAP, '_ochered_spisok.html'))
io.open(P, 'w', encoding='utf-8').write(t)
print('правок внесено: %d из %d' % (sdelano, len(pravki)))
print('обрезка осталась: %s' % ('line-clamp' in t))
