# -*- coding: utf-8 -*-
"""Строка «Директор»: длинная причина растягивала выпадающий список на полэкрана."""
import io, os, shutil, time
P = r'C:\centro2\app\templates\centro.html'
t = io.open(P, encoding='utf-8').read()
staro = '.direktor-metka{'
novo = '.direktor-ryad select{max-width:300px}\n.direktor-metka{'
if '.direktor-ryad select{max-width' in t:
    print('уже правлено')
elif t.count(staro) == 1:
    b = os.path.join(r'C:\centro2\_bekap', time.strftime('direktor-shirina-%Y%m%d-%H%M%S'))
    os.makedirs(b, exist_ok=True)
    shutil.copy2(P, os.path.join(b, 'centro.html'))
    io.open(P, 'w', encoding='utf-8').write(t.replace(staro, novo, 1))
    print('правка внесена')
else:
    print('ЯКОРЬ: %d' % t.count(staro))
