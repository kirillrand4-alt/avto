# -*- coding: utf-8 -*-
"""Сноска блока: фраза про счётчик «в работе слева» — только на «Списке компаний».

На «Статистике» слева нет никакого счётчика «в работе», и фраза отсылает к несуществующему.
"""
import io
import os
import shutil
import time

P = r'C:\centro2\app\templates\_statblok.html'
t = io.open(P, encoding='utf-8').read()
staro = '«Взял в работу» — только этот статус; «в работе» слева — все обработанные.'
novo = ("«Взял в работу» — только этот статус{% if stat_forma.endswith('/centro/spisok') %};"
        " «в работе» слева — все обработанные{% endif %}.")
if "stat_forma.endswith('/centro/spisok')" in t:
    print('уже правлено')
elif t.count(staro) == 1:
    bekap = os.path.join(r'C:\centro2\_bekap', time.strftime('snoska-%Y%m%d-%H%M%S'))
    os.makedirs(bekap, exist_ok=True)
    shutil.copy2(P, os.path.join(bekap, '_statblok.html'))
    io.open(P, 'w', encoding='utf-8').write(t.replace(staro, novo, 1))
    print('сноска поправлена')
else:
    print('ЯКОРЬ: %d вхождений — не правлю' % t.count(staro))
